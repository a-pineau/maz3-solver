import torch as T
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
import numpy as np


class DeepQNetwork(nn.Module):
    def __init__(self, lr, input_dims, fc1_dims, fc2_dims, n_actions) -> None:
        super(DeepQNetwork, self).__init__()
        self.input_dims = input_dims
        self.fc1_dims = fc1_dims
        self.fc2_dims = fc2_dims
        self.n_actions = n_actions

        # layers
        self.fc1 = nn.Linear(*self.input_dims, self.fc1_dims)  # inputs
        self.fc2 = nn.Linear(self.fc1_dims, self.fc2_dims)  # hidden
        self.fc3 = nn.Linear(self.fc2_dims, self.n_actions)  # outputs

        self.optimizer = optim.Adam(self.parameters(), lr=lr)
        self.loss = nn.MSELoss()
        self.device = T.device("cuda:0" if T.cuda.is_available() else "cpu")
        self.to(self.device)

    def forward(self, state):
        x = F.relu(self.fc1(state))
        x = F.relu(self.fc2(x))
        actions = self.fc3(x)

        return actions


class Agent:
    def __init__(
        self,
        gamma,
        epsilon,
        lr,
        input_dims,
        batch_size,
        n_actions,
        min_epsilon=0.01,
        epsilon_decay=1e-4,
        max_mem_size=100_000,
    ) -> None:
        
        self.gamma = gamma
        self.epsilon = epsilon
        self.max_epsilon = epsilon
        self.min_epsilon = min_epsilon
        self.epsilon_decay = epsilon_decay
        self.lr = lr
        self.batch_size = batch_size
        self.mem_cntr = 0
        self.mem_size = max_mem_size
        self.epsilon_decay = epsilon_decay
        self.action_space = [i for i in range(n_actions)]
        
        self.current_decision = None
        self.last_decision = None
        self.n_exploration = 0
        self.n_exploitation = 0

        self.Q_eval = DeepQNetwork(
            self.lr,
            n_actions=n_actions,
            input_dims=input_dims,
            fc1_dims=256,
            fc2_dims=256,
        )
        
        self.state_memory = np.zeros((self.mem_size, *input_dims), dtype=np.float32)
        self.new_state_memory = np.zeros((self.mem_size, *input_dims), dtype=np.float32)
        self.action_memory = np.zeros(self.mem_size, dtype=np.int32)
        self.reward_memory = np.zeros(self.mem_size, dtype=np.float32)
        self.terminal_memory = np.zeros(self.mem_size, dtype=np.bool)

    def store_transitions(self, state, action, reward, new_state, terminal):
        index = self.mem_cntr % self.mem_size  # wrapping around
        
        self.state_memory[index] = state
        self.new_state_memory[index] = new_state
        self.reward_memory[index] = reward
        self.action_memory[index] = action
        self.terminal_memory[index] = terminal

        self.mem_cntr += 1

    def choose_action(self, observation):
        if np.random.random() > self.epsilon:
            self.n_exploitation += 1
            self.current_decision = "exploitation"
            state = T.tensor([observation]).to(self.Q_eval.device)
            actions = self.Q_eval.forward(state)
            action = T.argmax(actions).item()
        else:
            self.n_exploration += 1
            self.current_decision = "exploration"
            action = np.random.choice(self.action_space)

        return action

    def learn(self):
        if self.mem_cntr < self.batch_size:
            return None

        self.Q_eval.optimizer.zero_grad()

        max_mem = min(self.mem_cntr, self.mem_size)
        batch = np.random.choice(max_mem, self.batch_size, replace=False)
        batch_index = np.arange(self.batch_size, dtype=np.int32)

        # np array -> pytorch tensor
        state_batch = T.tensor(self.state_memory[batch]).to(self.Q_eval.device)
        new_state_batch = T.tensor(self.new_state_memory[batch]).to(self.Q_eval.device)
        reward_batch = T.tensor(self.reward_memory[batch]).to(self.Q_eval.device)
        terminal_batch = T.tensor(self.terminal_memory[batch]).to(self.Q_eval.device)

        action_batch = self.action_memory[batch]

        q_eval = self.Q_eval.forward(state_batch)[batch_index, action_batch]
        q_next = self.Q_eval.forward(new_state_batch)
        q_next[terminal_batch] = 0.0

        q_target = reward_batch + self.gamma * T.max(q_next, dim=1)[0]

        loss = self.Q_eval.loss(q_target, q_eval).to(self.Q_eval.device)
        loss.backward()
        self.Q_eval.optimizer.step()

        if self.epsilon > self.min_epsilon:
            self.epsilon = self.epsilon - self.epsilon_decay
        else:
            self.epsilon = self.min_epsilon
