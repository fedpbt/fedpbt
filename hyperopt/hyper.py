from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import random

import ray
from ray.tune import run, sample_from
from ray.tune.schedulers import AsyncHyperBandScheduler
from ray.tune.suggest.hyperopt import HyperOptSearch
from hyperopt import hp

if __name__ == "__main__":
    ray.init(redis_password="hyperopt")
    space = {
        "lr": hp.choice("lr", [1e-2, 5e-3, 1e-3, 5e-4, 1e-4, 5e-5, 1e-5, 5e-6]),
        "gamma": hp.choice("gamma", [0.997, 0.995, 0.99, 0.98, 0.97, 0.95, 0.9, 0.85, 0.8]),
        "entropy_coeff": hp.choice("entropy_coeff", [0.0, 0.001, 0.01])
    }
    current_best_params = [ 
        {
            "lr": 4,
            "gamma": 4,
            "entropy_coeff": 1,
        }
    ] 
    config = {
        "num_samples": 1000,
        "config": {
            "lambda": 0.95,
            "clip_rewards": True,
            "clip_param": 0.1,
            "vf_clip_param": 10.0,
            "kl_coeff": 0.5,
            "train_batch_size": 5000,
            "sample_batch_size": 100,
            "sgd_minibatch_size": 500,
            "num_sgd_iter": 10,
            "num_workers": 15,
            "num_envs_per_worker": 5,
            "batch_mode": "truncate_episodes",
            "observation_filter": "NoFilter",
            "vf_share_layers": True,
            "num_gpus": 1,
            "env": "BreakoutNoFrameskip-v4",
            # TODO: Are these necessary?
            #"lr": 1e-3,
            #"gamma": 0.99,
            #"entropy_coeff": 0.001,
        },
        "stop": {
            "timesteps_total": 50000000,
        },
    }
from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

import random
import argparse 

import ray
from ray.tune import run, sample_from, grid_search

parser = argparse.ArgumentParser(
    description='Run Grid Search')
parser.add_argument("--env", type=str, 
    choices=['HalfCheetah-v2', 'Humanoid-v2', 'Hopper-v2',
    "BreakoutNoFrameskip-v4", "PongNoFrameskip-v4", "QbertNoFrameskip-v4", "BeamRiderNoFrameskip-v4", 
    "MountainCarContinuous-v0"], default="MountainCarContinuous-v0")
parser.add_argument("--tune", type=bool, default=True)
parser.add_argument("--pbt", type=bool, default=False)
parser.add_argument("--num_workers", type=int, default=1)
parser.add_argument("--gpus", type=int, default=0.4)
# parser.add_argument("--cpus", type=int, default=1)
parser.add_argument("--num_agents", type=int, default=1)
parser.add_argument("--interval", type=int, default=4)
parser.add_argument("--temp", type=float, default=1.5)
parser.add_argument("--quantile", type=float, default=0.25)
parser.add_argument("--resample_probability", type=float, default=0.25)
parser.add_argument("--algo", type=str, default='PPO')
parser.add_argument("--lr", type=list, 
    default=[1e-2, 1e-4, 5e-6])
parser.add_argument("--gamma", type=list, default=[0.997, 0.97, 0.8])
parser.add_argument("--entropy_coeff", type=list, default=[0.01, 0.0])
parser.add_argument("--explore_params", type=list, default=["lr", "gamma"])
args = parser.parse_args()
#import pdb; pdb.set_trace()
if args.env=="BreakoutNoFrameskip-v4" or args.env=="QbertNoFrameskip-v4" or args.env=="BeamRiderNoFrameskip-v4":
    parser.add_argument("--Lambda", type=float, default=0.95)
    parser.add_argument("--kl_coeff", type=float, default=0.5)
    parser.add_argument("--clip_rewards", type=bool, default=True)
    parser.add_argument("--clip_param", type=float, default=0.1)
    parser.add_argument("--vf_clip_param", type=float, default=10.0)
    parser.add_argument("--vf_loss_coeff", type=float, default=1.0)
    parser.add_argument("--num_sgd_iter", type=int, default=10)
    parser.add_argument("--sgd_minibatch_size", type=int, default=500)
    parser.add_argument("--sample_batch_size", type=int, default=100)
    parser.add_argument("--train_batch_size", type=int, default=5000)
    parser.add_argument("--free_log_std", type=bool, default=False)
    parser.add_argument("--use_gae", type=bool, default=True)
    parser.add_argument("--batch_mode", type=str, default="truncate_episodes")
    parser.add_argument("--vf_share_layers", type=bool, default=False)
    parser.add_argument("--observation_filter", type=str, default="NoFilter")
    parser.add_argument("--grad_clip", type=float, default=None)
    parser.add_argument("--is_atari", type=bool, default=True)
    parser.add_argument("--dim", type=int, default=84)
    parser.add_argument("--max_steps", type=int, default=1e7)
elif args.env=='HalfCheetah-v2':
    parser.add_argument("--Lambda", type=float, default=0.95)
    parser.add_argument("--kl_coeff", type=float, default=1.0)
    parser.add_argument("--clip_rewards", type=bool, default=False)
    parser.add_argument("--clip_param", type=float, default=0.2)
    parser.add_argument("--vf_clip_param", type=float, default=10.0)
    parser.add_argument("--vf_loss_coeff", type=float, default=1.0)
    parser.add_argument("--num_sgd_iter", type=int, default=32)
    parser.add_argument("--sgd_minibatch_size", type=int, default=4096)
    parser.add_argument("--sample_batch_size", type=int, default=200)
    parser.add_argument("--train_batch_size", type=int, default=65536)
    parser.add_argument("--free_log_std", type=bool, default=False)
    parser.add_argument("--use_gae", type=bool, default=True)
    parser.add_argument("--batch_mode", type=str, default="truncate_episodes")
    parser.add_argument("--vf_share_layers", type=bool, default=False)
    parser.add_argument("--observation_filter", type=str, default="MeanStdFilter")
    parser.add_argument("--grad_clip", type=float, default=0.5)
    parser.add_argument("--is_atari", type=bool, default=False)
    parser.add_argument("--dim", type=int, default=84)
    parser.add_argument("--max_steps", type=int, default=1e8)
elif args.env=='Humanoid-v2':
    parser.add_argument("--Lambda", type=float, default=1.0)
    parser.add_argument("--kl_coeff", type=float, default=1.0)
    parser.add_argument("--clip_rewards", type=bool, default=False)
    parser.add_argument("--clip_param", type=float, default=0.3)
    parser.add_argument("--vf_clip_param", type=float, default=10.0)
    parser.add_argument("--vf_loss_coeff", type=float, default=1.0)
    parser.add_argument("--num_sgd_iter", type=int, default=20)
    parser.add_argument("--sgd_minibatch_size", type=int, default=32678)
    parser.add_argument("--sample_batch_size", type=int, default=200)
    parser.add_argument("--train_batch_size", type=int, default=320000)
    parser.add_argument("--free_log_std", type=bool, default=True)
    parser.add_argument("--use_gae", type=bool, default=False)
    parser.add_argument("--batch_mode", type=str, default="complete_episodes")
    parser.add_argument("--vf_share_layers", type=bool, default=False)
    parser.add_argument("--observation_filter", type=str, default="MeanStdFilter")
    parser.add_argument("--grad_clip", type=float, default=None)
    parser.add_argument("--is_atari", type=bool, default=False)
    parser.add_argument("--dim", type=int, default=84)
    parser.add_argument("--max_steps", type=int, default=1e8)
elif args.env=="MountainCarContinuous-v0":
    parser.add_argument("--Lambda", type=float, default=1.0)
    parser.add_argument("--kl_coeff", type=float, default=0.2)
    parser.add_argument("--clip_rewards", type=bool, default=False)
    parser.add_argument("--clip_param", type=float, default=0.3)
    parser.add_argument("--vf_clip_param", type=float, default=10.0)
    parser.add_argument("--vf_loss_coeff", type=float, default=1.0)
    parser.add_argument("--num_sgd_iter", type=int, default=30)
    parser.add_argument("--sgd_minibatch_size", type=int, default=128)
    parser.add_argument("--sample_batch_size", type=int, default=200)
    parser.add_argument("--train_batch_size", type=int, default=4000)
    parser.add_argument("--free_log_std", type=bool, default=False)
    parser.add_argument("--use_gae", type=bool, default=True)
    parser.add_argument("--batch_mode", type=str, default="truncate_episodes")
    parser.add_argument("--vf_share_layers", type=bool, default=False)
    parser.add_argument("--observation_filter", type=str, default="NoFilter")
    parser.add_argument("--grad_clip", type=float, default=None)
    parser.add_argument("--is_atari", type=bool, default=False)
    parser.add_argument("--dim", type=int, default=84)
    parser.add_argument("--max_steps", type=int, default=1e5)
elif args.env=='Hopper-v2':
    parser.add_argument("--Lambda", type=float, default=1.0)
    parser.add_argument("--kl_coeff", type=float, default=1.0)
    parser.add_argument("--clip_rewards", type=bool, default=False)
    parser.add_argument("--clip_param", type=float, default=0.3)
    parser.add_argument("--vf_clip_param", type=float, default=10.0)
    parser.add_argument("--vf_loss_coeff", type=float, default=1.0)
    parser.add_argument("--num_sgd_iter", type=int, default=20)
    parser.add_argument("--sgd_minibatch_size", type=int, default=32678)
    parser.add_argument("--sample_batch_size", type=int, default=200)
    parser.add_argument("--train_batch_size", type=int, default=160000)
    parser.add_argument("--free_log_std", type=bool, default=False)
    parser.add_argument("--use_gae", type=bool, default=True)
    parser.add_argument("--batch_mode", type=str, default="complete_episodes")
    parser.add_argument("--vf_share_layers", type=bool, default=False)
    parser.add_argument("--observation_filter", type=str, default="MeanStdFilter")
    parser.add_argument("--grad_clip", type=float, default=None)
    parser.add_argument("--is_atari", type=bool, default=False)
    parser.add_argument("--dim", type=int, default=84)
    parser.add_argument("--max_steps", type=int, default=2e7)
elif args.env=="PongNoFrameskip-v4":
    parser.add_argument("--Lambda", type=float, default=0.95)
    parser.add_argument("--kl_coeff", type=float, default=0.5)
    parser.add_argument("--clip_rewards", type=bool, default=True)
    parser.add_argument("--clip_param", type=float, default=0.1)
    parser.add_argument("--vf_clip_param", type=float, default=10.0)
    parser.add_argument("--vf_loss_coeff", type=float, default=1.0)
    parser.add_argument("--num_sgd_iter", type=int, default=10)
    parser.add_argument("--sgd_minibatch_size", type=int, default=500)
    parser.add_argument("--sample_batch_size", type=int, default=20)
    parser.add_argument("--train_batch_size", type=int, default=5000)
    parser.add_argument("--free_log_std", type=bool, default=False)
    parser.add_argument("--use_gae", type=bool, default=True)
    parser.add_argument("--batch_mode", type=str, default="truncate_episodes")
    parser.add_argument("--vf_share_layers", type=bool, default=True)
    parser.add_argument("--observation_filter", type=str, default="NoFilter")
    parser.add_argument("--grad_clip", type=float, default=None)
    parser.add_argument("--is_atari", type=bool, default=True)
    parser.add_argument("--dim", type=int, default=42)
    parser.add_argument("--max_steps", type=int, default=3e6)
args = parser.parse_args()
ray.init(redis_password='gridsearch')
algo = HyperOptSearch(
    space,
    max_concurrent=4,
    metric="episode_reward_mean",
    mode="max",
    #points_to_evaluate=current_best_params
)
scheduler = AsyncHyperBandScheduler(metric="episode_reward_mean", mode="max")
run(
    "PPO",
    name="hyperopt_breakout_50m",
    search_alg=algo,
    #scheduler=scheduler,
    **config
)
run(
    "PPO",
    #stop={"timesteps_total": 500000000},
    config={
            "num_workers": args.num_workers,
            "num_gpus": args.gpus,
            "env": args.env,
            # can't access args.lambda, it's a syntax error
            "lambda": args.Lambda,
            #"gamma": grid_search(args.gamma),
            "gamma": 0.95,
            "kl_coeff": args.kl_coeff,
            "clip_rewards": args.clip_rewards,
            "clip_param": args.clip_param,
            "vf_clip_param": args.vf_clip_param,
            "vf_loss_coeff": args.vf_loss_coeff,
            #"entropy_coeff": grid_search(args.entropy_coeff),
            "entropy_coeff": 0,
            "num_sgd_iter": args.num_sgd_iter,
            "sgd_minibatch_size": args.sgd_minibatch_size,
            "sample_batch_size": args.sample_batch_size,
            #"lr": grid_search(args.lr),
            "lr": 0.0001,
            "num_envs_per_worker": 5,
            # divide batch between agents, because we'll replicate it later
            "train_batch_size": args.train_batch_size,
            "model": {
                "free_log_std": args.free_log_std,
                "dim": args.dim,
            },
            "use_gae": args.use_gae,
            "batch_mode": args.batch_mode,
            "vf_share_layers": args.vf_share_layers,
            "observation_filter": args.observation_filter,
            "grad_clip": args.grad_clip,
        },
)
