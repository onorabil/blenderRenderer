import shutil
import glob
import json
from os import getcwd
from os.path import join
from pathlib import Path
from tqdm import tqdm


def read_label(path):
    with open(path, 'r') as f:
        l = f.readline().split()
    return int(l[0])


DATASET = 'bdataset'
wd = Path(getcwd())
root = wd.parent
data_path = Path(join(wd, 'out'))

Path(join(root, DATASET)).mkdir(parents=True, exist_ok=True)

images = sorted(glob.glob(str(data_path / '*rgb.png'), recursive=True))
normals = sorted(glob.glob(str(data_path / '*normal.exr'), recursive=True))
depths = sorted(glob.glob(str(data_path / '*depth.exr'), recursive=True))
labels = sorted(glob.glob(str(data_path / '*label.txt'), recursive=True))

STEP = 3

JSON_TRAIN_DATA = []
JSON_TEST_DATA = []

index = 0
loop = tqdm(zip(images, normals, depths, labels))
for i, (img, normal, depth, label_path) in enumerate(loop):
    shutil.copy(img, join(root, DATASET))
    shutil.copy(normal, join(root, DATASET))
    shutil.copy(depth, join(root, DATASET))
    label = read_label(label_path)
    (JSON_TEST_DATA if i % STEP == 0 else JSON_TRAIN_DATA).append({
        "image": Path(img).name,
        "normal": Path(normal).name,
        "depth": Path(depth).name,
        "label": label,
    })

with open(join(root, DATASET, "train.json"), "w") as f:
    json.dump(JSON_TRAIN_DATA, f)
with open(join(root, DATASET, "test.json"), "w") as f:
    json.dump(JSON_TEST_DATA, f)
