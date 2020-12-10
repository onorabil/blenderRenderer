#!/bin/sh

model_name=scuffed_plane
materials=$(ls poliigon_material_samples)

for m in $materials ; do ./run.sh $model_name $m ; done
