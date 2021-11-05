from python_code.channel.channel import ISIAWGNChannel
from python_code.channel.modulator import BPSKModulator
from python_code.utils.config_singleton import Config
import numpy as np
import torch

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

conf = Config()


class Augmenter1:
    @staticmethod
    def augment(transmitted_word, h, snr):
        binary_mask = torch.rand_like(transmitted_word) >= 0.5
        new_transmitted_word = (transmitted_word + binary_mask) % 2
        # encoding - errors correction code
        c = new_transmitted_word.cpu().numpy()
        # add zero bits
        padded_c = np.concatenate([c, np.zeros([c.shape[0], conf.memory_length])], axis=1)
        # from channel dataset
        s = BPSKModulator.modulate(padded_c)
        # transmit through noisy channel
        new_received_word = ISIAWGNChannel.transmit(s=s, h=h.cpu().numpy(), snr=snr,
                                                    memory_length=conf.memory_length)
        return torch.Tensor(new_received_word).to(device), new_transmitted_word