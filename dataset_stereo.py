import shutil
import glob
import json
from os import getcwd
from os.path import join
from pathlib import Path
from tqdm import tqdm
import argparse


def read_rotation(path):
    with open(path, 'r') as f:
        l = [float(a) for a in f.readline().split()]
    return l


parser = argparse.ArgumentParser(description="dataset tree structure")
parser.add_argument("dest", type=str, default="bdataset")
opt = parser.parse_args()

DATASET = opt.dest
wd = Path(getcwd())
root = wd.parent
data_path = Path(join(wd, 'out'))

Path(join(root, DATASET)).mkdir(parents=True, exist_ok=True)

left_images = sorted(glob.glob(str(data_path / '*stereo_L.png'), recursive=True))
right_images = sorted(glob.glob(str(data_path / '*stereo_R.png'), recursive=True))
left_depths = sorted(glob.glob(str(data_path / '*depth_L.exr'), recursive=True))
right_depths = sorted(glob.glob(str(data_path / '*depth_R.exr'), recursive=True))
left_normals = sorted(glob.glob(str(data_path / '*normal_L.exr'), recursive=True))
right_normals = sorted(glob.glob(str(data_path / '*normal_R.exr'), recursive=True))
rotations = sorted(glob.glob(str(data_path / '*rotation.txt'), recursive=True))

STEP = 3

JSON_TRAIN_DATA = []
JSON_TEST_DATA = []

index = 0
loop = tqdm(zip(left_images, right_images, left_depths, right_depths, left_normals, right_normals, rotations))
for i, (left_img, right_img, left_depth, right_depth, left_normal, right_normal, rotation_path) in enumerate(loop):
    shutil.copy(left_img, join(root, DATASET))
    shutil.copy(right_img, join(root, DATASET))
    shutil.copy(left_depth, join(root, DATASET))
    shutil.copy(right_depth, join(root, DATASET))
    shutil.copy(left_normal, join(root, DATASET))
    shutil.copy(right_normal, join(root, DATASET))
    rotation = read_rotation(rotation_path)
    (JSON_TEST_DATA if i % STEP == 0 else JSON_TRAIN_DATA).append({
        "imageL": Path(left_img).name,
        "imageR": Path(right_img).name,
        "depthL": Path(left_depth).name,
        "depthR": Path(right_depth).name,
        "normalL": Path(left_normal).name,
        "normalR": Path(right_normal).name,
        "rotation": rotation,
    })

with open(join(root, DATASET, "train.json"), "w") as f:
    json.dump(JSON_TRAIN_DATA, f)
with open(join(root, DATASET, "test.json"), "w") as f:
    json.dump(JSON_TEST_DATA, f)