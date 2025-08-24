import numpy as np
import sys
import os

# Add the parent directory to the path (so 'plant' is recognized as a package)
script_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(script_dir)  # This is the project root
sys.path.insert(0, parent_dir)

from plant.plant import Plant

plant = Plant()

print(plant.q_bi)
print(plant.w_bi)
