import datetime
import os
import rospy
import numpy as np
import sys
import torch
import time
from roslaunch.parent import ROSLaunchParent

from blimp_env.envs import ResidualPlanarNavigateEnv
from config import generate_config, save_config
from my_ppo import MyPPO
from util import *
from scipy.io import savemat

if __name__ == '__main__':
    os.system(". /home/yang/catkin_ws/src/AutonomousBlimpDRL/blimp_env/blimp_env/envs/script/cleanup.sh")
    time_limit = 1200
    for i in range(2):
        # rospy.core._shutdown_flag = False
        # exp setup

        # Wind index
        j = 0
        # Buoyancy index
        m = 1
        seed = 10
        ENV = ResidualPlanarNavigateEnv
        AGENT = MyPPO
        n_env = 1
        robot_id = 0

        env_name = ENV.__name__
        agent_name = AGENT.__name__
        exp_name = env_name + "_" + agent_name

        env_default_config = ENV.default_config()
        duration = env_default_config["duration"]
        simulation_frequency = env_default_config["simulation_frequency"]
        policy_frequency = env_default_config["policy_frequency"]

        days = 2
        one_day_ts = 24 * 3600 * policy_frequency
        TIMESTEP = int(days * one_day_ts)

        trigger_dist = 5
        init_alt = 100
        as_ds_threshold = 0
        steps = 3
        target_kl = 0.02
        uniform = True
        full_obs = False
        display = False  # Display the training progress
        cpu = False
        gui = True
        rnn = True
        close_prev_sim = True if robot_id == 0 else False

        # exp_config
        os.chdir("/home/yang/catkin_ws/src/AutonomousBlimpDRL/RL/rl")

        if i == 0:
            pid = True
            exp_time = "S1_pid_uni"
            test_name = "PID1_cover"
            weight_interval = [1, 1]
        elif i == 1:
            pid = False
            exp_time = "S1_hinf_uni"
            test_name = "Hinf1_cover"
            weight_interval = [1, 1]


        exp_path = os.path.join("/home/yang/catkin_ws/src/AutonomousBlimpDRL/RL/rl/agent", exp_name, exp_time)
        exp_config = {
            "final_model_save_path": os.path.join(exp_path, "final_model"),
        }

        # parameter
        windspeed = 0.5 * j
        buoyancy = 0.93 + 0.07 * m

        # if float(sys.argv[4]) == 0.0:
        #     traj = "square"
        # elif float(sys.argv[4]) == 1.0:
        #     traj = "coil"
        traj = "coil"
        # env_config
        robot_id = 0
        close_prev_sim = True if robot_id == 0 else False
        env_config = {
            "simulation": {
                "gui": gui,
                "auto_start_simulation": True,
                "enable_meshes": True,
                "enable_meshes": True,
                "enable_wind": True,
                "enable_wind_sampling": True,
                "wind_speed": windspeed,
                "wind_direction": (1, 0),
                "enable_buoyancy_sampling": True,
                "buoyancy_range": [buoyancy, buoyancy],
                "position": (0, 0, init_alt),
            },
            "observation": {
                "weight_interval": weight_interval,
                "enable_actuator_status": full_obs,
                "DBG_OBS": False,
                "enable_next_goal": full_obs,
                "enable_airspeed_sensor": full_obs,
            },
            "action": {
                "type": "SimpleContinuousAction",
                "act_noise_stdv": 0.05,
                # Joint action restriction!
                "max_servo": 1,
                "min_servo": -1,
                "max_thrust": 1,
                "min_thrust": -1,
                "dbg_act": False,
            },
            "n_workers": n_env,
            "seed": seed,
            "weight_interval": weight_interval,
            # "duration": 100000,
            "MIMO_controller": False,
            "uniform": uniform,
            "pid": pid,
            "DBG": False,
            "evaluation_mode": False,
            "real_experiment": True,
            "duration": duration,
            "test_mode": True,
            "as_ds_threshold": as_ds_threshold,
        }

        # agent_config
        agent_config = {
            "clip_ratio": 0.5,
            "lam": 0.95,
            "gamma": 0.999,
            "cpu": cpu,
            "rnn": rnn,
            "log": False,
            "seed": seed,
            "total_steps": TIMESTEP,
            "n_env": n_env,
            "target_kl": target_kl,
            "max_episode_length": np.Inf,
            "rate": policy_frequency,
            "display": display,
        }


        def generate_coil(points, height, speed=5):
            li = []
            nwp_layer = 8
            for i in range(points - 1):
                x = 0
                y = 200 * i + 200
                wp = (x, y, -init_alt, speed)
                li.append(wp)
            wp = (0, 120 * (points-1) + 400, -init_alt + height, speed)
            li.append(wp)
            return li


        coil = generate_coil(3, 80)

        wp_list = coil

        target_config = {
            "type": "MultiGoal",
            "target_name_space": "goal_",
            "trigger_dist": trigger_dist,
            "wp_list": wp_list,
            "enable_random_goal": False,
        }
        if "target" in env_config:
            env_config["target"].update(target_config)
        else:
            env_config["target"] = target_config

        # start testing
        config = generate_config(
            agent_name=agent_name,
            exp_config=exp_config,
            env_config=env_config,
            agent_config=agent_config,
        )
        # exp_training(**config, cpu=cpu, steps=steps, rate=policy_frequency)

        # def exp_training(exp_config, env_config, agent_config, cpu, steps, rate):
        # Original training function
        rate = policy_frequency
        env = ResidualPlanarNavigateEnv(env_config)
        agent = AGENT(env=env, **agent_config).load(exp_config["final_model_save_path"])
        torch.set_default_dtype(torch.float32)
        device = torch.device('cpu')
        if torch.cuda.is_available() and not cpu:
            device = torch.device('cuda')
        rospy.sleep(0.5)
        obs = env.reset()
        done_count = 0
        zeta = []
        eta = []
        epsilon = []
        delta = []
        reward = []
        distance = []
        t = []
        position = []
        goal_position = []
        valid_count = 0
        k = 0
        init_time = time.time()
        failed = False
        while done_count < steps:
            action = agent.predict(obs, device)
            obs, rewards, dones, info = env.step(action=action.squeeze())
            if info['obs_info']['distance'] <= env.target_type.trigger_dist:
                done_count += 1
                env.base_controller.reset()
                # if done_count % 1 == 0:
                #     agent.pi.reset_hc()
                # agent.pi.reset_hc()
                if env.pid:
                    env.yaw_basectrl.reset()
                    env.alt_basectrl.reset()
                    env.vel_basectrl.reset()
            # if float(sys.argv[4]) == 1.0:
            #     if done_count == 5:
            #         valid_count = 1
            # elif float(sys.argv[4]) == 0:
            #     if done_count == 4:
            #         valid_count = 1
            if done_count == 2:
                valid_count = 1
            zeta.append(info['obs_info']['joint_action'][0])
            eta.append(info['obs_info']['joint_action'][1])
            epsilon.append(info['obs_info']['joint_action'][2])
            delta.append(info['obs_info']['joint_action'][3])
            reward.append(rewards)
            t.append(valid_count)
            distance.append(info['obs_info']['distance'])
            position.append(info['obs_info']['position'])
            goal_position.append(info['obs_info']['goal_position'])
            k = k + 1
            if k % rate == 0:
                print(f"Progress: {done_count} / {steps} ( {100 * done_count / steps} % )\n"
                      # f"Test: {i+1}\n"
                      f"Controller: {test_name}\n"
                      f"Wind: {j}\n"
                      f"Buoyancy: {m}\n"
                      # f"Steps: {k}\n"
                      f"Observation: {obs}\n"
                      f"PPO action: {action[0]}\n"
                      # f"Reward: {rewards}\n"
                      # f"Distance: {info['obs_info']['distance']}\n"
                      f"Target distance: {env.target_type.trigger_dist}")
                # print("Theta_target", self.theta_target)
                # print("Theta: ", self.pos.theta)
                # print("Delta theta", self.delta_theta)
                print("\n")
            rospy.Rate(rate).sleep()
            if (time.time() - init_time) >= time_limit:
                failed = True
                break
        dict = {'done_count': done_count, 'zeta': zeta, 'eta': eta, 'epsilon': epsilon, 'delta': delta,
                'reward': reward, 'valid_count': t, 'distance': distance, 'position': position,
                'goal_position': goal_position}
        if not failed:
            file_name = test_name + "_W" + str(j) + "_B" + str(m) + ".mat"
        else:
            file_name = test_name + "_W" + str(j) + "_B" + str(m) + "_failed.mat"
        savemat(file_name, dict)
