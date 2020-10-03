# rotary-phone-hack
##### Python code for controlling a rotary phone from a Raspberry Pi

## Setup
```sh
# From RPI
git clone git@github.com:jtschoonhoven/rotary-phone-hack.git
cd rotary-phone-hack
pip3 install -r requirements.txt
```

Pygame is preinstalled on Raspbian OS but must be installed manually on other distros

```sh
sudo apt-get install -y libsdl1.2-dev libsdl-mixer1.2-dev
pip3 install pygame
```

## Quickstart
```sh
python3 phonehack
```
