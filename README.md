Synthetic dataset creator using Blender, an obj model and texture from poliigon.com

Contains parts from the material converter addon, available here:
https://help.poliigon.com/en/articles/2540839-poliigon-material-converter-addon-for-blender

### Models and Materials
https://drive.google.com/drive/folders/1IlFDUHxvjXrwdo9GdHM764n9HKwnzfml?usp=sharing

### How to run

1. Download a texture
- go to poliigon.com
- create an account
- download a {free} texture

2. Render

```sh
blender -b --python main.py -- models/goat_willow_leaf/model_normalized.obj --views_x=3 --views_y=3 --views_z=3 --material materials/Leaf_4K --output_folder output --seed 1
```

output file names will be : model_render_seed_rotation_(layer)

3. Preview Data using jupyter notebook

### USAGE

usage: blender [-h] [--views_x VIEWS_X] [--views_y VIEWS_Y]
               [--views_z VIEWS_Z] [--seed SEED]
               [--output_folder OUTPUT_FOLDER] [--color_depth COLOR_DEPTH]
               [--material MATERIAL [MATERIAL ...]]
               [--output_name OUTPUT_NAME]
               obj

Renders given obj file by rotation a camera around it.

positional arguments:
  obj                   Path to the obj file to be rendered.

optional arguments:
  -h, --help            show this help message and exit
  --views_x VIEWS_X
  --views_y VIEWS_Y
  --views_z VIEWS_Z
  --seed SEED           used to randomize vertices.
  --output_folder OUTPUT_FOLDER
                        The path the output will be dumped to.
  --color_depth COLOR_DEPTH
                        Number of bit per channel used for output. Either 8 or
                        16.
  --material MATERIAL [MATERIAL ...]
                        Material name. Check README.md
  --output_name OUTPUT_NAME
                        name of the output file

