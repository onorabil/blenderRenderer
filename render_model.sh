#!/bin/sh

model=$1
material=$2

blender -b --python main.py -- $model --material $material --views_x=4 --views_y=4 --views_z=4 --output_folder output