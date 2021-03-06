# BlenderRenderer
Synthetic dataset creator using Blender Python API and [poliigon material converter](https://help.poliigon.com/en/articles/2540839-poliigon-material-converter-addon-for-blender). <br>

## Requirements
Python 3.8 or later with all [requirements.txt](https://github.com/onorabil/blenderRenderer/blob/main/requirements.txt) dependencies installed. To install run:
```bash
$ pip install -r requirements.txt
```

### Resources
Objects, Materials + example dataset and the commands used to create it<br>
https://drive.google.com/drive/folders/1IlFDUHxvjXrwdo9GdHM764n9HKwnzfml?usp=sharing

### USAGE

Renders given object file by rotating a camera around it.

```bash
$ blender -b --python main.py -- [-h] [--views_x VIEWS_X] [--views_y VIEWS_Y]
                                 [--views_z VIEWS_Z] [--resolution RESOLUTION] [--seed SEED
                                 [--output_folder OUTPUT_FOLDER] [--color_depth COLOR_DEPTH]
                                 [--material MATERIAL [MATERIAL ...]] 
                                 [--output_name OUTPUT_NAME] [--class_name CLASS_NAME]
                                 obj
```

To generate the required folder structure run this command<br>
It will generate the bdataset dir in the parent directory using the output

```bash
$ python dataset.py
```