#!/bin/sh

model_name=$1
materials=$(ls poliigon_material_samples)

for m in $materials ; do ./run.sh $model_name $m ; done
