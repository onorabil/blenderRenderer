#!/bin/sh

model_name=$1
model=models/$model_name/model_normalized.obj
material=$2

blender -b --python main.py -- $model --material $material --views_x=4 --views_y=4 --views_z=4 --output_folder output/$model_name'_'$material
