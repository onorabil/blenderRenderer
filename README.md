Synthetic dataset creator using Blender, an obj model and texture from poliigon.com

Contains parts from the material converter addon, available here:
https://help.poliigon.com/en/articles/2540839-poliigon-material-converter-addon-for-blender

### How to run

1. Download a texture
- go to poliigon.com
- crete an account
- download a {free} texture

2. Render

```sh
blender -b --python main.py -- models/goat_willow_leaf/model_normalized.obj --views_x=3 --views_y=3 --views_z=3 --material materials/Leaf_4K --output_folder output --seed 1
```

output file names will be : model_render_seed_rotation_(layer)

3. Preview Data using jupyter notebook

#### TODO
- add params for mesh / symmetric mesh instead of loaded model
- add optical flow

