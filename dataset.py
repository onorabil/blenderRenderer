import json
import shutil
from os import getcwd
from os.path import join
from pathlib import Path

DATASET='bdataset'

train_fname = "train.csv"
test_fname = "test.csv"
class_fname = "class.csv"
wd = Path(getcwd())
root = wd.parent
data_path = Path(join(wd, 'output'))


def convert(box):
    min_x, max_x, min_y, max_y = box
    min_x = min(max(0, min_x), 1)
    max_x = min(max(0, max_x), 1)
    min_y = min(max(0, min_y), 1)
    max_y = min(max(0, max_y), 1)
    x = (min_x + max_x) / 2.0
    y = 1 - (min_y + max_y) / 2.0
    w = max_x - min_x
    h = max_y - min_y
    return x, y, w, h


def create_annotation(classes, json_path, label_path):
    with open(json_path, 'r') as json_file:
        data = json.load(json_file)
    assert data is not None

    with open(label_path, 'w') as label_file:
        label_file.write(" ".join(str(item) for item in [classes.index(data['label']), *convert(data['bbox'])]))


classes = open(join(data_path, class_fname)).read().strip().split()
train_json = open(join(data_path, train_fname)).read().strip().split()
test_json = open(join(data_path, test_fname)).read().strip().split()

Path(join(root, DATASET, 'images', 'train')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'images', 'test')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'depth', 'train')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'depth', 'test')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'seg', 'train')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'seg', 'test')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'normals', 'train')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'normals', 'test')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'labels', 'train')).mkdir(parents=True, exist_ok=True)
Path(join(root, DATASET, 'labels', 'test')).mkdir(parents=True, exist_ok=True)

for json_fname in train_json:
    fname = json_fname.split('.')[0]
    img_fname = fname + f'_render.png'
    depth_fname = fname + f'_depth.exr'
    seg_fname = fname + f'_albedo.exr'
    normal_fname = fname + f'_normal.exr'
    img_path = join(data_path, img_fname)
    depth_path = join(data_path, depth_fname)
    seg_path = join(data_path, seg_fname)
    normal_path = join(data_path, normal_fname)
    json_path = join(data_path, json_fname)
    shutil.copy(img_path, join(root, DATASET, 'images', 'train', fname + f'.png'))
    shutil.copy(depth_path, join(root, DATASET, 'depth', 'train', fname + f'.exr'))
    shutil.copy(seg_path, join(root, DATASET, 'seg', 'train', fname + f'.exr'))
    shutil.copy(normal_path, join(root, DATASET, 'normals', 'train', fname + f'.exr'))
    create_annotation(classes, json_path, join(root, DATASET, 'labels', 'train', fname + f'.txt'))
    
for json_fname in test_json:
    fname = json_fname.split('.')[0]
    img_fname = fname + f'_render.png'
    depth_fname = fname + f'_depth.exr'
    seg_fname = fname + f'_albedo.exr'
    normal_fname = fname + f'_normal.exr'
    img_path = join(data_path, img_fname)
    depth_path = join(data_path, depth_fname)
    seg_path = join(data_path, seg_fname)
    normal_path = join(data_path, normal_fname)
    json_path = join(data_path, json_fname)
    shutil.copy(img_path, join(root, DATASET, 'images', 'test', fname + f'.png'))
    shutil.copy(depth_path, join(root, DATASET, 'depth', 'test', fname + f'.exr'))
    shutil.copy(seg_path, join(root, DATASET, 'seg', 'test', fname + f'.exr'))
    shutil.copy(normal_path, join(root, DATASET, 'normals', 'test', fname + f'.exr'))
    create_annotation(classes, json_path, join(root, DATASET, 'labels', 'test', fname + f'.txt'))