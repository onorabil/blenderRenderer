# BlenderRenderer
Synthetic dataset creator using Blender Python API and poliigon material converter. <br>
<br>
Contains parts from the material converter addon, available here:<br>
https://help.poliigon.com/en/articles/2540839-poliigon-material-converter-addon-for-blender<br>

## Requirements
Python 3.8 or later with all [requirements.txt](https://github.com/onorabil/blenderRenderer/blob/main/requirements.txt) dependencies installed. To install run:
```bash
$ pip install -r requirements.txt
```

### Resources
Objects, Materials + example dataset and the commands used to create it<br>
https://drive.google.com/drive/folders/1IlFDUHxvjXrwdo9GdHM764n9HKwnzfml?usp=sharing

### USAGE

```bash
$ blender -b --python main.py -- [-h] [--views_x VIEWS_X] [--views_y VIEWS_Y]
                                 [--views_z VIEWS_Z] [--resolution RESOLUTION] [--seed SEED
                                 [--output_folder OUTPUT_FOLDER] [--color_depth COLOR_DEPTH]
                                 [--material MATERIAL [MATERIAL ...]]
                                 [--output_name OUTPUT_NAME]
                                 obj
```

Renders given object file by rotating a camera around it.<br>
<br>
positional arguments:<br>
  obj                   Path to the obj file to be rendered.<br>
<br>
optional arguments:<br>
  -h, --help            show this help message and exit<br>
  --views_x VIEWS_X<br>
  --views_y VIEWS_Y<br>
  --views_z VIEWS_Z<br>
  --resolution RESOLUTION<br>
  --seed SEED           used to randomize vertices.<br>
  --output_folder OUTPUT_FOLDER<br>
                        The path the output will be dumped to.<br>
  --color_depth COLOR_DEPTH<br>
                        Number of bit per channel used for output. Either 8 or
                        16.<br>
  --material MATERIAL [MATERIAL ...]<br>
                        Material file path.<br>
  --output_name OUTPUT_NAME<br>
                        name of the output file<br>

