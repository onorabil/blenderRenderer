Synthetic dataset creator using Blender, an obj model and texture from poliigon.com

Contains parts from the material converter addon, available here:
https://help.poliigon.com/en/articles/2540839-poliigon-material-converter-addon-for-blender 

### How to run

1. Download a texture
- go to poliigon.com
- crete an account
- download a {free} texture
- place all images in the ```poliigon_sample_textures/textureName_resolution``` folder ( e.g, ```TilesMarbleSageGreenBrickBondHoned001_3K```)

2. Render

```sh
blender -b --python main.py -- models/1a04e3eab45ca15dd86060f189eb133/models/model_normalized.obj --views_x=5 --views_y=5 --views_z=5 --output_folder output
```

#### TODO
- add params for mesh / symmetric mesh instead of loaded model
- add optical flow

