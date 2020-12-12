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
blender -b --python main.py -- models/goat_willow_leaf/model_normalized.obj --material materials/GroundMoss001_3K --output_folder output
```

#### TODO
- add params for mesh / symmetric mesh instead of loaded model
- add optical flow

