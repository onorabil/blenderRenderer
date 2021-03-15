# BlenderRenderer
Synthetic dataset creator using Blender Python API and [poliigon material converter](https://help.poliigon.com/en/articles/2540839-poliigon-material-converter-addon-for-blender). <br>

## Requirements
Python 3.8 or later with all [requirements.txt](https://github.com/onorabil/blenderRenderer/blob/main/requirements.txt) dependencies installed. To install run:
```bash
$ pip install -r requirements.txt
```

### Resources
Objects, Materials + examples<br>
https://drive.google.com/drive/folders/1IlFDUHxvjXrwdo9GdHM764n9HKwnzfml?usp=sharing

### USAGE

Renders a set of scenes built from a json file.

```bash
$ blender -b --python render.py -- json
```

To generate the required folder structure run this command<br>
It will generate the bdataset dir in the parent directory using the output

```bash
$ python dataset.py
```

### JSON STRUCT

- `classes`: list containing the classes of the objects
- `batches`: a list containing scene information
    - `imports`: a list containing imports (objects, materials) tuples
        - `object`/`fbx`: use object if you import an obj file and fbx if you import an fbx file
            - `path`: path to the object file
            - `name`: the name of the object, used in blender as an id
            - `class`: object class
            - `position`: position of the object
            - `rotation`: rotation of the object
            - `scale`: scale of the object
            - `seed`: used to randomize vertices, 0 if not used
        - `materials`: a list of materials to assign to the object
            - `path`: path to the material file
            - `name`: name of the material
    - `scene`: contains scene configurations
        - `camera`: 
            - `position`: initial position of the camera
            - `rotation`: initial rotation of the camera
        - `lights`: list of light configurations
            - `type`: `SUN`, `POINT`, other Blender light types.
            - `position`: position of the light
            - `rotation`: rotation of the light
            - `energy`: intensity of the light
        - `render`: render configuration
            - `path`: the output directory path
            - `resolution`: the resolution of the image, `witdh`=`height`=`resolution`
            - `eevee`: use the eevee engine if true else cycles (set false if you want to output the optical flow).
            next you should use either views for a static render or frames if you use an animation file
            - `views`:
                - `x`: angles on the x axis [start, stop(not included), step]
                - `y`: angles on the y axis [start, stop(not included), step]
                - `z`: angles on the z axis [start, stop(not included), step]
            - `frames`: frames to render an animation [start, stop(not included), step]