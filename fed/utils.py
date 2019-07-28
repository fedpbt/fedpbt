import gym
import math
import random
import numpy as np
#from easydict import EasyDict

import ray
from ray.tune.registry import register_env
from ray import tune
from ray.rllib.env.multi_agent_env import MultiAgentEnv
from ray.rllib.env.atari_wrappers import is_atari, wrap_deepmind

# PBT_QUANTILE = 0.25

def make_multiagent(args):
    class MultiEnv(MultiAgentEnv):
        def __init__(self):
            self.agents = [gym.make(args.env) for _ in range(args.num_agents)]
            if args.is_atari:
                self.agents = [wrap_deepmind(env, dim=args.dim) for env in self.agents]
            self.dones = set()
            self.observation_space = self.agents[0].observation_space
            self.action_space = self.agents[0].action_space

        def reset(self):
            self.dones = set()
            return {i: a.reset() for i, a in enumerate(self.agents)}

        def step(self, action_dict):
            obs, rew, done, info = {}, {}, {}, {}
            for i, action in action_dict.items():
                obs[i], rew[i], done[i], info[i] = self.agents[i].step(action)
                if done[i]:
                    self.dones.add(i)
            done["__all__"] = len(self.dones) == len(self.agents)
            return obs, rew, done, info

    return MultiEnv

def make_fed_env(args):   
    FedEnv = make_multiagent(args)
    env_name = "multienv_FedRL"
    register_env(env_name, lambda _: FedEnv())
    return env_name

def gen_policy_graphs(args):
    single_env = gym.make(args.env)
    if args.is_atari:
        single_env = wrap_deepmind(single_env, dim=args.dim)
    obs_space = single_env.observation_space
    act_space = single_env.action_space
    policy_graphs = {f'agent_{i}': (None, obs_space, act_space, {}) 
         for i in range(args.num_agents)}
    return policy_graphs

def policy_mapping_fn(agent_id):
    return f'agent_{agent_id}'
def change_weights(weights, i):
    """
    Helper function for FedQ-Learning
    """
    dct = {}
    for key, val in weights.items():
        # new_key = key
        still_here = key[:6]
        there_after = key[7:]
        # new_key[6] = i
        new_key = still_here + str(i) + there_after
        dct[new_key] = val
    # print(dct.keys())
    return dct

def synchronize(agent, weights, args):
    """
    Helper function to synchronize weights of the multiagent
    """
    weights_to_set = {f'agent_{i}': weights 
         for i in range(args.num_agents)}
    # weights_to_set = {f'agent_{i}': change_weights(weights, i) 
    #    for i in range(num_agents)}
    agent.set_weights(weights_to_set)

def uniform_initialize(agent, args):
    """
    Helper function for uniform initialization
    """
    new_weights = agent.get_weights(["agent_0"]).get("agent_0")
    # print(new_weights.keys())
    synchronize(agent, new_weights, args)

def compute_softmax_weighted_avg(weights, alphas, args):
    """
    Helper function to compute weighted avg of weights weighted by alphas
    Weights and alphas must have same keys. Uses softmax.
    params:
        weights - dictionary
        alphas - dictionary
    returns:
        new_weights - array
    """
    def softmax(x, beta=args.temp, length=args.num_agents):
        """Compute softmax values for each sets of scores in x."""
        e_x = np.exp(beta * (x - np.max(x)))
        return (e_x / e_x.sum()).reshape(length, 1)
    
    alpha_vals = np.array(list(alphas.values()))
    soft = softmax(alpha_vals)
    weight_vals = np.array(list(weights.values()))
    new_weights = sum(np.multiply(weight_vals, soft))
    return new_weights

def compute_reward_weighted_avg(weights, alphas, args):
    alpha_vals = np.array(list(alphas.values()))
    weight_vals = np.array(list(weights.values()))
    soft = (alpha_vals/alpha_vals.sum()).reshape(args.num_agents, 1)
    new_weights = sum(np.multiply(weight_vals, soft))
    return new_weights

def reward_weighted_update(agent, result, args): 
    """
    Helper function to synchronize weights of multiagent via
    reward-weighted avg of weights
    """
    all_weights = agent.get_weights()
    policy_reward_mean = result['policy_reward_mean']
    if policy_reward_mean:
        new_weights = compute_reward_weighted_avg(all_weights, policy_reward_mean, args) 
        synchronize(agent, new_weights, args) 

def softmax_reward_weighted_update(agent, result, args):
    """
    Helper function to synchronize weights of multiagent via
    softmax reward-weighted avg of weights with specific temperature
    """
    all_weights = agent.get_weights()
    policy_reward_mean = result['policy_reward_mean']
    if policy_reward_mean:
        new_weights = compute_softmax_weighted_avg(all_weights, policy_reward_mean, args)
        synchronize(agent, new_weights, args)
        explore(agent, policy_reward_mean, args)

def population_based_train(agent, result, args):
    """
    Helper function to implement population based training
    """
    all_weights = agent.get_weights()
    agents = [f'agent_{id}' for id in range(args.num_agents)]
    policy_reward_mean = result['policy_reward_mean']
    if policy_reward_mean:
        # import pdb; pdb.set_trace()
        sorted_rewards = sorted(policy_reward_mean.items(), key=lambda kv: kv[1])
        upper_quantile = [kv[0] for kv in sorted_rewards[int(math.floor(args.quantile * -args.num_agents)):]]
        lower_quantile = [kv[0] for kv in sorted_rewards[:int(math.ceil(args.quantile * args.num_agents))]]
        new_weights = {agent_id: all_weights[agent_id] if agent_id not in lower_quantile else all_weights[random.choice(upper_quantile)] 
         for agent_id in agents}
        agent.set_weights(new_weights)
        # explore(agent, lower_quantile)

def explore(agent, policy_reward_mean, args):
    """
    Helper function to explore hyperparams (currently just lr)
    """
    from ray.rllib.utils.schedules import ConstantSchedule
    sorted_rewards = sorted(policy_reward_mean.items(), key=lambda kv: kv[1])
    upper_quantile = [kv[0] for kv in sorted_rewards[int(math.floor(args.quantile * -args.num_agents)):]]
    lower_quantile = [kv[0] for kv in sorted_rewards[:int(math.ceil(args.quantile * args.num_agents))]]
    for agent_id in lower_quantile:
        policy_graph = agent.get_policy(agent_id)
        new_policy_graph = agent.get_policy(random.choice(upper_quantile))
        if "lr" in args.explore_params:
            exemplar = new_policy_graph.cur_lr
            distribution = args.lr
            new_val = explore_helper(exemplar, distribution, args)
            policy_graph.lr_schedule = ConstantSchedule(new_val)
        if "gamma" in args.explore_params:
            param = "gamma"
            exemplar = new_policy_graph.config[param]
            distribution = args.gammas
            new_val = explore_helper(exemplar, distribution, args)
            policy_graph.config[param] = new_val
        if "entropy_coeff" in args.explore_params:
            param = "entropy_coeff"
            exemplar = new_policy_graph.config[param]
            distribution = args.entropy_coeffs
            new_val = explore_helper(exemplar, distribution, args)
            policy_graph.config[param] = new_val

def explore_helper(exemplar, distribution, args):
    if random.random() < args.resample_probability or \
                    exemplar not in distribution:
                new_val = random.choice(distribution)
    elif random.random() > 0.5:
        new_val = distribution[max(
            0,
            distribution.index(exemplar) - 1)]
    else:
        new_val = distribution[min(
            len(distribution) - 1,
            distribution.index(exemplar) + 1)]
    return new_val


def fed_pbt_train(args):
    def fed_learn(metrics):
        result = metrics["result"]
        trainer = metrics["trainer"]
        info = result["info"]
        optimizer = trainer.optimizer
        #result['timesteps_total'] = result['timesteps_total'] * num_agents
        result['timesteps_total'] = info['num_steps_trained']
        result['episode_reward_mean'] = np.mean(list(result['policy_reward_mean'].values())) if result['policy_reward_mean'] else np.nan
        result['episode_reward_best'] = np.max(list(result['policy_reward_mean'].values())) if result['policy_reward_mean'] else np.nan
        result['federated'] = "No federation"
        if result['training_iteration'] == 1:
            uniform_initialize(trainer, args) 
        elif result['training_iteration'] % args.interval == 0:
            result['federated'] = f"Federation with {args.temp}"
            # update weights
            #reward_weighted_update(agent, result, num_agents)
            softmax_reward_weighted_update(trainer, result, args) 
            # clear buffer, don't want smoothing here
            optimizer.episode_history = []
    return fed_learn

def fed_train(args):
    num_agents = args.num_agents
    if args.tune:
        temp_schedule = args.temp_schedule
        init_temp = temp_schedule[0]
        init_temp_1, init_temp_2, init_temp_3, init_temp_4 = init_temp
        hotter_temp = temp_schedule[1]
        hotter_temp_1, hotter_temp_2, hotter_temp_3, hotter_temp_4 = hotter_temp
        temp_shift = temp_schedule[2]
        fed_schedule = args.fed_schedule
        init_iters = fed_schedule[0]
        init_iters_1, init_iters_2, init_iters_3, init_iters_4 = init_iters
        increased_iters = fed_schedule[1]
        increased_iters_1, increased_iters_2, increased_iters_3, increased_iters_4 = increased_iters
        fed_shift = fed_schedule[2]
        def fed_learn_1(info):
            return
    #       get stuff out of info
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            num_iters = init_iters_1
            temperature = init_temp_1
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            # potentially scale up
            if result['timesteps_total'] > fed_shift:
                num_iters = increased_iters_1
            if result['timesteps_total'] > temp_shift:
                temperature = hotter_temp_1
            # correct result reporting
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            result['federated'] = "No federation"
            if result['training_iteration'] == 1:
                uniform_initialize(agent, num_agents)
            elif result['training_iteration'] % num_iters == 0:
                result['federated'] = f"Federation with {temperature}"
                # update weights
                #reward_weighted_update(agent, result, num_agents)
                softmax_reward_weighted_update(agent, result, num_agents, temperature, explore_dict={"lr": args.lr})
                # clear buffer, don't want smoothing here
                optimizer.episode_history = []
        def fed_learn_2(info):
    #       get stuff out of info
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            num_iters = init_iters_2
            temperature = init_temp_2
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            # potentially scale up
            if result['timesteps_total'] > fed_shift:
                num_iters = increased_iters_2
            if result['timesteps_total'] > temp_shift:
                temperature = hotter_temp_2
            # correct result reporting
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            result['federated'] = "No federation"
            if result['training_iteration'] == 1:
                uniform_initialize(agent, num_agents)
            elif result['training_iteration'] % num_iters == 0:
                result['federated'] = f"Federation with {temperature}"
                # update weights
                #reward_weighted_update(agent, result, num_agents)
                softmax_reward_weighted_update(agent, result, num_agents, temperature, explore_dict={"lr": args.lr})
                # clear buffer, don't want smoothing here
                optimizer.episode_history = []
        def fed_learn_3(info):
    #       get stuff out of info
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            num_iters = init_iters_3
            temperature = init_temp_3
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            # potentially scale up
            if result['timesteps_total'] > fed_shift:
                num_iters = increased_iters_3
            if result['timesteps_total'] > temp_shift:
                temperature = hotter_temp_3
            # correct result reporting
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            result['federated'] = "No federation"
            if result['training_iteration'] == 1:
                uniform_initialize(agent, num_agents)
            elif result['training_iteration'] % num_iters == 0:
                result['federated'] = f"Federation with {temperature}"
                # update weights
                #reward_weighted_update(agent, result, num_agents)
                softmax_reward_weighted_update(agent, result, num_agents, temperature, explore_dict={"lr": args.lr})
                # clear buffer, don't want smoothing here
                optimizer.episode_history = []
        def fed_learn_4(info):
    #       get stuff out of info
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            num_iters = init_iters_4
            temperature = init_temp_4
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            # potentially scale up
            if result['timesteps_total'] > fed_shift:
                num_iters = increased_iters_4
            if result['timesteps_total'] > temp_shift:
                temperature = hotter_temp_4
            # correct result reporting
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            result['federated'] = "No federation"
            if result['training_iteration'] == 1:
                uniform_initialize(agent, num_agents)
            elif result['training_iteration'] % num_iters == 0:
                result['federated'] = f"Federation with {temperature}"
                # update weights
                #reward_weighted_update(agent, result, num_agents)
                softmax_reward_weighted_update(agent, result, num_agents, temperature, explore_dict={"lr": args.lr})
                # clear buffer, don't want smoothing here
                optimizer.episode_history = []
        return fed_learn_1, fed_learn_2, fed_learn_3, fed_learn_4
    elif args.pbt:
        iters = args.num_iters
        num_iters_1, num_iters_2, num_iters_3, num_iters_4 = iters
        def pbt_1(info):
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            if result['training_iteration'] % num_iters_1 == 0:
                population_based_train(agent, result, num_agents)
                optimizer.episode_history = []
        def pbt_2(info):
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            if result['training_iteration'] % num_iters_2 == 0:
                population_based_train(agent, result, num_agents)
                optimizer.episode_history = []
        def pbt_3(info):
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            if result['training_iteration'] % num_iters_3 == 0:
                population_based_train(agent, result, num_agents)
                optimizer.episode_history = []
        def pbt_4(info):
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            if result['training_iteration'] % num_iters_4 == 0:
                population_based_train(agent, result, num_agents)
                optimizer.episode_history = []
        return pbt_1, pbt_2, pbt_3, pbt_4
    else:
        temperature = args.temperature
        num_iters = args.num_iters
        def fed_learn(info):
    #       get stuff out of info
            result = info["result"]
            agent = info["trainer"]
            optimizer = agent.optimizer
            result['timesteps_total'] = result['timesteps_total'] * num_agents
            # correct result reporting
            result['episode_reward_mean'] = result['episode_reward_mean']/num_agents
            result['episode_reward_max'] = result['episode_reward_max']/num_agents
            result['episode_reward_min'] = result['episode_reward_min']/num_agents
            result['federated'] = "No federation"
            if result['training_iteration'] == 1:
                uniform_initialize(agent, num_agents)
            elif result['training_iteration'] % num_iters == 0:
                result['federated'] = f"Federation with {temperature}"
                # update weights
                reward_weighted_update(agent, result, num_agents)
                # softmax_reward_weighted_update(agent, result, num_agents, temperature)
                # clear buffer, don't want smoothing here
                optimizer.episode_history = []
        return fed_learn
