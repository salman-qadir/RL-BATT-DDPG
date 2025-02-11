# -*- coding: utf-8 -*-
"""
Created on Fri Oct 29 2021

@author: Saehong Park
"""
#
#import os
#os.getcwd()
#os.chdir(/percorso/file)
#import sys
#
#def get_script_path():
#    return os.path.dirname(os.path.realpath(sys.argv[0]))

import gym
import random
import torch
import numpy as np
from collections import deque
import matplotlib.pyplot as plt
from settings_file import*


from ddpg_agent import Agent
import pdb
import ipdb

import logz
import scipy.signal
import gym
# import gym_dfn
from gym_dfn.envs.dfn_env import *


from gym_dfn.envs.ParamFile_LCO2 import p
import statistics
import pickle
import os

import argparse

#------------ For MAC-OS
import os

os.environ['KMP_DUPLICATE_LIB_OK']='True'
#------------
#FUNCTIONS


#------------ For PCA 
from numpy import linalg as LA
import scipy.io as sio
data = sio.loadmat('PCA_DFN_info.mat')
data_mu = data['time_states_mu']
data_std = data['time_states_std']
data_PCA = data['PCA_trans']


# normalize states of the system
def normalize_states(state):

    csn_max = 3.0542e+04
    csp_max = 4.9521e+04
    ce0 = 1.0e3
    T_amb = 298.15

    # ipdb.set_trace()

    N_cavgn = p['Nxn']-1
    N_cavgp = p['Nxp']-1
    N_cex = p['Nxn']-1 + p['Nxs']-1 + p['Nxp']-1

    # PCA Normalize the states.
    c_avgn_concentration = state[:N_cavgn]
    c_avgp_concentration = state[N_cavgn : (N_cavgn + N_cavgp)]
    c_ex_concentration = state[(N_cavgn+N_cavgp):(N_cavgn+N_cavgp+N_cex)]

    time_states = np.concatenate((c_avgn_concentration, c_avgp_concentration, c_ex_concentration), axis=0)
    time_states_arr = time_states.reshape([time_states.shape[0],1])
    standard_states_arr = (time_states_arr - data_mu)/data_std
    pca_states_arr = np.dot(data_PCA, standard_states_arr)
    pca_states_arr_nmz = pca_states_arr / LA.norm(pca_states_arr,2)

    pca_states_nmz = pca_states_arr_nmz.reshape([pca_states_arr_nmz.shape[0],]) # arr -> list

    # Temp = (state[-1] - 298 - 10) / (320-298)
    # Temp = np.array([Temp])

    # # Cocatenate
    
    Temp = (state[-1] - 298 - 10) / (320-298)
    Temp = np.array([Temp])

    second_part = np.concatenate((pca_states_nmz,Temp),axis=0)

    norm_state = second_part
    
    return norm_state

# compute actual action from normalized action 
def denormalize_input(input_value, min_OUTPUT_value, max_OUTPUT_value):
    
    output_value=(1+input_value)*(max_OUTPUT_value-min_OUTPUT_value)/2+min_OUTPUT_value
    
    return output_value


def eval_policy(policy, eval_episodes=10):

    eval_env = DFN(sett=settings, cont_sett=control_settings)

    avg_reward = 0.
    avg_temp_vio = 0.
    avg_etasLN_vio = 0.
    avg_chg_time = 0.


    for _ in range(eval_episodes):

        initial_conditions['init_v']=np.random.uniform(low=3.5, high=3.7)
        initial_conditions['init_t']=np.random.uniform(low=298, high=305)
        
        state, done = eval_env.reset(init_v=initial_conditions['init_v'],init_t=initial_conditions['init_t']), False
        norm_state = normalize_states(state)


        ACTION_VEC = []
        T_VEC = []
        ETAS_VEC = []

        while not done:
            norm_action = agent.act(norm_state, add_noise=False)
            #actual action
            applied_action=denormalize_input(norm_action,
                                                     eval_env.action_space.low[0],
                                                     eval_env.action_space.high[0])
            next_state, reward, done, _ = eval_env.step(applied_action)

            ACTION_VEC.append(applied_action[0])
            T_VEC.append(eval_env.Temp[0])
            ETAS_VEC.append(eval_env.etasLn[0])

            norm_state = normalize_states(next_state)

            avg_reward += reward

        avg_temp_vio += np.max(np.array(T_VEC))
        avg_etasLN_vio += np.min(np.array(ETAS_VEC))
        avg_chg_time += len(ACTION_VEC)


    avg_reward /= eval_episodes
    avg_temp_vio /= eval_episodes
    avg_etasLN_vio /= eval_episodes
    avg_chg_time /= eval_episodes

    avg_MIN_etasLN_vio = avg_etasLN_vio
    avg_MAX_temp_vio = avg_temp_vio

    print("---------------------------------------")
    print(f"Evaluation over {eval_episodes} episodes: {avg_reward:.3f}")
    print("---------------------------------------")

    return avg_reward, avg_MAX_temp_vio, avg_MIN_etasLN_vio, avg_chg_time




# the normalization of states and inputs is required for improving the training of the network 
    
# function for training the ddpg agent
def ddpg(n_episodes=3000, i_training=1):
    scores_list = []
    checkpoints_list=[]


    # Save the initial parameters of actor-critic networks.
    i_episode = 0
    checkpoints_list.append(i_episode)
    try:
        os.makedirs('results/training_results/training'+str(i_training)+'/episode'+str(i_episode))
    except:
        pass
    
    torch.save(agent.actor_local.state_dict(), 'results/training_results/training'+str(i_training)+'/episode'+str(i_episode)+'/checkpoint_actor_'+str(i_episode)+'.pth')
    torch.save(agent.critic_local.state_dict(), 'results/training_results/training'+str(i_training)+'/episode'+str(i_episode)+'/checkpoint_critic_'+str(i_episode)+'.pth')
    torch.save(agent.actor_optimizer.state_dict(), 'results/training_results/training'+str(i_training)+'/episode'+str(i_episode)+'/checkpoint_actor_optimizer_'+str(i_episode)+'.pth')
    torch.save(agent.critic_optimizer.state_dict(), 'results/training_results/training'+str(i_training)+'/episode'+str(i_episode)+'/checkpoint_critic_optimizer_'+str(i_episode)+'.pth')

    # Evaluate the initial (untrained) policy
    print('Evaluate first.')
    evaluations = [eval_policy(agent)]

    for i_episode in range(1, n_episodes+1):
        

#            
        #random initial values
        initial_conditions['init_v']=np.random.uniform(low=3.5, high=3.7)
        initial_conditions['init_t']=np.random.uniform(low=298, high=305)

        # reset the environment and the agent
        state=env.reset(init_v=initial_conditions['init_v'], init_t=initial_conditions['init_t'])
        norm_state=normalize_states(state)
        
        agent.reset() 
        
        score = 0
        done=False
        cont=0
        
        V_VEC=[]
        T_VEC=[]

        while not done or score>control_settings['max_negative_score']:
            
            #normalize states
#            norm_state=normalize_states(env)

            #compute normalized action
            norm_action = agent.act(norm_state, add_noise=True)
            
            #actual action
            applied_action=denormalize_input(norm_action,
                                                     env.action_space.low[0],
                                                     env.action_space.high[0])
            
            #apply action
            next_state,reward,done,b=env.step(applied_action)
            norm_next_state=normalize_states(next_state)

            # a and b are not used

            # normalize next state
#            norm_next_state=normalize_states(env)
            
            V_VEC.append(env.info['V'])
            T_VEC.append(env.info['T'])
            
            #update the agent according to norm_states, norm_next_states, reward, and norm_action
            agent.step(norm_state, norm_action, reward, norm_next_state, done)
            try:
                score += reward
            except:
                pdb.set_trace()    
            cont+=1
            if done:
                break
            
            norm_state=norm_next_state

        # ipdb.set_trace()
        print("Training", i_training)
        print("\rEpisode number ", i_episode)
        print("reward: ", score)

        
        #save the vector of all the scores
        scores_list.append(score)

        if (i_episode % settings['periodic_test']) == 0 :
        #save the checkpoint for actor, critic and optimizer (for loading the agent)
        

            checkpoints_list.append(i_episode)
            try:
                os.makedirs('results/training_results/training'+str(i_training)+'/episode'+str(i_episode))
            except:
                pass
            
            torch.save(agent.actor_local.state_dict(), 'results/training_results/training'+str(i_training)+'/episode'+str(i_episode)+'/checkpoint_actor_'+str(i_episode)+'.pth')
            torch.save(agent.critic_local.state_dict(), 'results/training_results/training'+str(i_training)+'/episode'+str(i_episode)+'/checkpoint_critic_'+str(i_episode)+'.pth')
            torch.save(agent.actor_optimizer.state_dict(), 'results/training_results/training'+str(i_training)+'/episode'+str(i_episode)+'/checkpoint_actor_optimizer_'+str(i_episode)+'.pth')
            torch.save(agent.critic_optimizer.state_dict(), 'results/training_results/training'+str(i_training)+'/episode'+str(i_episode)+'/checkpoint_critic_optimizer_'+str(i_episode)+'.pth')

        

        if (i_episode % settings['periodic_test']) == 0 :
            # Perform evaluation test
            evaluations.append(eval_policy(agent))
            try:
                os.makedirs('results/testing_results/training'+str(i_training))
            except:
                pass
            
            np.save('results/testing_results/training'+str(i_training)+'/eval.npy',evaluations)


    return scores_list, checkpoints_list






#-------------------------------------------------------------------------------------
#MAIN

initial_conditions={}

# assign the environment
env = DFN(sett=settings, cont_sett=control_settings)

# parser
parser = argparse.ArgumentParser()
parser.add_argument('--id', type = int)
args = parser.parse_args()

# Seeding
i_seed = args.id
i_training = i_seed
np.random.seed(i_seed)
torch.manual_seed(i_seed)

#TRAINING simulation
total_returns_list_with_exploration=[]


#-------------------------------------------------------------------------------------
#assign the agent which is a ddpg
agent = Agent(state_size=5, action_size=1, random_seed=i_seed)  # the number of state is 496.

# call the function for training the agent
returns_list, checkpoints_list = ddpg(n_episodes=settings['number_of_training_episodes'], i_training=i_training)
total_returns_list_with_exploration.append(returns_list)
    

with open("results/training_results/total_returns_list_with_exploration.txt", "wb") as fp:   #Pickling, \\ -> / for mac.
   pickle.dump(total_returns_list_with_exploration, fp)

with open("results/training_results/checkpoints_list.txt", "wb") as fp:   #Pickling
   pickle.dump(checkpoints_list, fp)