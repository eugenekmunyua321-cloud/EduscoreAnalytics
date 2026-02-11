import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

class Eduscore:
    def __init__(self, data):
        self.data = data

    def analyze(self):
        # Perform analysis
        return self.data.describe()

    def visualize(self):
        plt.plot(self.data)
        plt.show()

if __name__ == '__main__':
    # Assuming 'data.csv' contains the necessary data
    data = pd.read_csv('data.csv')
    eduscore = Eduscore(data)
    print(eduscore.analyze())
    eduscore.visualize()