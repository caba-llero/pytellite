# Pytellite

Pytellite is an open-source spacecraft attitude simulator. It allows to easily test control laws and visualize the satellite motion through a web app. Please note that as of September 2025, the app is in early stages of development. For more information, please visit https://caba.lle.ro/portfolio. 

The as of 9/23/2025, the attitude estimation feature is disabled, and will be live once I carry out more tests. You can find the error state multiplicative extended Kalman filter used to simulate the attitude estimation as a standalone project here: https://github.com/caba-llero/Error-state-MEKF

## Testing Pytellite online
Visit https://www.pytellite.org

## Running Pytellite locally
1) Python 3.10+ recommended
2) Install dependencies:
```
pip install -r requirements.txt
```
3) Run the web app (dev):
```
python app.py
```
Then open: http://127.0.0.1:8000/ 

## Upcoming features
Pytellite will soon propagate the spacecraft's orbit, which will allow for more complex pointing types (such as nadir and Sun pointing, and detumbling). It will also allow to implement perturbation torques. Stay tuned!
