from python_code.channel.channels_hyperparams import MEMORY_LENGTH, N_USER
from python_code.utils.constants import ChannelModes
from python_code.utils.python_utils import sample_random_mimo_word
from python_code.utils.trellis_utils import calculate_states, calculate_mimo_states
from python_code.utils.config_singleton import Config
from typing import Tuple
import torch

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

conf = Config()


class AdaptiveAugmenter:
    """
    The proposed augmentations scheme. Calculates centers and variances for each class as specified in the paper,
    then smooths the estimate via a window running mean with alpha = 0.3
    """

    def __init__(self):
        super().__init__()
        self._centers = None
        self._stds = None
        self._alpha1 = 1  # mean smoothing hyperparameter
        self._alpha2 = 1  # std smoothing hyperparameter

    def augment(self, received_word: torch.Tensor, transmitted_word: torch.Tensor, h: torch.Tensor, snr: float,
                update_hyper_params: bool = False) -> Tuple[torch.Tensor, torch.Tensor]:
        # if pilot, then update_hyper_params is True and we update the centers and stds internal parameters
        if update_hyper_params:
            # first calculate estimated noise pattern
            cur_centers, cur_stds = self.estimate_cur_params(received_word, transmitted_word)
            # average the current centers & stds estimates with previous estimates to reduce noise
            self.update_centers_stds(cur_centers, cur_stds)

        new_transmitted_word = torch.rand_like(transmitted_word) >= 0.5
        # calculate states of transmitted, and copy to variable that will hold the new states for the new transmitted
        if conf.channel_type == ChannelModes.SISO.name:
            new_gt_states = calculate_states(MEMORY_LENGTH, new_transmitted_word)
        elif conf.channel_type == ChannelModes.MIMO.name:
            new_gt_states = calculate_mimo_states(N_USER, new_transmitted_word)
        else:
            raise ValueError("No such channel type!!!")
        new_received_word = torch.empty_like(received_word)

        # generate new words using the smoothed centers and stds
        for state in torch.unique(new_gt_states):
            state_ind = (new_gt_states == state)
            if conf.channel_type == ChannelModes.SISO.name:
                new_received_word[0, state_ind] = self._centers[state] + self._stds[state] * \
                                                  torch.randn_like(transmitted_word)[0, state_ind]
            elif conf.channel_type == ChannelModes.MIMO.name:
                new_received_word[state_ind] = self._centers[state] + self._stds[state] * \
                                               torch.randn_like(transmitted_word)[state_ind]
            else:
                raise ValueError("No such channel type!!!")
        new_received_word, new_transmitted_word = sample_random_mimo_word(new_received_word,
                                                                          new_transmitted_word,
                                                                          received_word)
        return new_received_word, new_transmitted_word.int()

    def update_centers_stds(self, cur_centers: torch.Tensor, cur_stds: torch.Tensor):
        """
        Update the parameters via temporal smoothing over a window with parameter alpha
        :param cur_centers: jth step estimated centers
        :param cur_stds:  jth step estimated stds
        :return: smoothed centers and stds vectors
        """

        # self._centers = cur_centers
        if self._centers is not None:
            self._centers = self._alpha1 * cur_centers + (1 - self._alpha1) * self._centers
        else:
            self._centers = cur_centers

        if self._stds is not None:
            self._stds = self._alpha2 * cur_stds + (1 - self._alpha2) * self._stds
        else:
            self._stds = cur_stds

    def estimate_cur_params(self, received_word: torch.Tensor, transmitted_word: torch.Tensor) -> Tuple[
        torch.Tensor, torch.Tensor]:
        """
        Estimate parameters of centers and stds in the jth step based on the known states of the pilot word.
        :param received_word: float words of channel values
        :param transmitted_word: binary word
        :return: updated centers and stds values
        """
        if conf.channel_type == ChannelModes.SISO.name:
            gt_states = calculate_states(MEMORY_LENGTH, transmitted_word)
            n_states = 2 ** MEMORY_LENGTH
        elif conf.channel_type == ChannelModes.MIMO.name:
            gt_states = calculate_mimo_states(N_USER, transmitted_word)
            n_states = 2 ** N_USER
        else:
            raise ValueError("No such channel type!!!")
        centers = torch.empty(n_states).to(device)
        stds = torch.empty(n_states).to(device)
        for state in range(n_states):
            state_ind = (gt_states == state)
            if conf.channel_type == ChannelModes.SISO.name:
                state_received = received_word[0, state_ind]
            elif conf.channel_type == ChannelModes.MIMO.name:
                state_received = received_word[state_ind]
            else:
                raise ValueError("No such channel type!!!")

            stds[state] = torch.std(state_received)
            if state_received.shape[0] > 0:
                centers[state] = torch.mean(state_received)
            else:
                centers[state] = 0
        stds[torch.isnan(stds)] = torch.mean(stds[~torch.isnan(stds)])
        return centers, stds

    @property
    def centers(self) -> torch.Tensor:
        return self._centers

    @property
    def stds(self) -> torch.Tensor:
        return self._stds
