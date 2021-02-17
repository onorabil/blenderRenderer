# A simple script that uses blender to render views of a single object by rotation the camera around it.
# Also produces depth map at the same time.
#
# Example:
# blender --background --python mytest.py -- --views 10 /path/to/my.obj
#

# TODO:
# - ?remesh vertices uniformly
# - select visible vertices
# - world_2_camera_view  >> check
#    cam = camera.getInverseMatrix()
#    cam.transpose()
#    cmra = camera.getData()
# - save world_2_camera_view + 6 orientation values
# - compute sparse flow (per vertex)
# FUTURE WORK
# + dense flow
# - add lights/motion blur/..


import argparse
import sys
import os
import bpy
import sys
from math import radians
import numpy as np
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
import json
import csv
import time
# HARDCODED STUFF


current_script_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current_script_path)


def getArgs():
    parser = argparse.ArgumentParser(
        description='Renders given obj file by rotation a camera around it.')
    # Views for the 3 euler angles
    parser.add_argument('--views_x', type=int, default=30)
    parser.add_argument('--views_y', type=int, default=30)
    parser.add_argument('--views_z', type=int, default=30)
    parser.add_argument('--resolution', type=int, default=256)

    parser.add_argument('--seed', type=int, default=0,
                        help='used to randomize vertices.')

    parser.add_argument('obj', type=str,
                        help='Path to the obj file to be rendered.')
    parser.add_argument('--output_folder', type=str, default='tmp',
                        help='The path the output will be dumped to.')
    parser.add_argument('--color_depth', type=str, default='8',
                        help='Number of bit per channel used for output. Either 8 or 16.')
    parser.add_argument('--material', type=str, nargs='+',
                        help='Material name. Check README.md')
    parser.add_argument('--output_name', type=str, default='out',
                        help='name of the output file')
    argv = sys.argv[sys.argv.index("--") + 1:]
    args = parser.parse_args(argv)
    return args


def blockPrint():
    open(os.devnull, 'a').close()
    old = os.dup(1)
    sys.stdout.flush()
    os.close(1)
    os.open(os.devnull, os.O_WRONLY)
    return old


def enablePrint(old):
    os.close(1)
    os.dup(old)
    os.close(old)


def remove_frame_number(fname):
    outRenderFileNamePadded = fname+"0001.exr"
    outRenderFileName = fname+".exr"
    if not os.path.exists(outRenderFileNamePadded):
        return
    if os.path.exists(outRenderFileName):
        os.remove(outRenderFileName)
    os.rename(outRenderFileNamePadded, outRenderFileName)


def parent_obj_to_camera(b_camera):
    origin = (0, 0, 0)
    b_empty = bpy.data.objects.new("Empty", None)
    b_empty.location = origin
    b_camera.parent = b_empty  # setup parenting

    bpy.context.collection.objects.link(b_empty)
    bpy.context.view_layer.objects.active = b_empty
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return b_empty


def get_vertices_and_edges(obj):
    vertices = np.array([list((obj.matrix_world @ v.co))
                         for v in obj.data.vertices])
    edges = np.array([list(i.vertices) for i in obj.data.edges])
    return vertices, edges


def get_BBox(camera, scene, vertices):
    minX, maxX = np.inf, -np.inf
    minY, maxY = np.inf, -np.inf

    for v in vertices:
        co2D = world_to_camera_view(scene, camera, Vector(v))
        if minX > co2D[0]:
            minX = co2D[0]
        if maxX < co2D[0]:
            maxX = co2D[0]
        if minY > co2D[1]:
            minY = co2D[1]
        if maxY < co2D[1]:
            maxY = co2D[1]

    return minX, maxX, minY, maxY


def get_camera_BBox(camera, scene, model):
    _, allVertices, _, mesh_data, _ = model
    BBoxes = []

    for mesh in mesh_data:
        vertices, _ = mesh_data[mesh]
        BBoxes = BBoxes + \
            [get_BBox(camera=camera, scene=scene, vertices=vertices)]

    return get_BBox(camera=camera, scene=scene, vertices=allVertices), BBoxes


def randomize_vertices(obj, seed):
    # randomize vertices using blender's vertex_random tool, SEED is an arg
    # 0.0025 is the maximum amount the vertices will move
    # uniform=1 and normal=0 made the model look better than the other configs
    if seed == 0:
        return
    obj.select_set(state=True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode='EDIT')
    bpy.ops.mesh.select_all(action='SELECT')
    bpy.ops.transform.vertex_random(
        offset=0.0025, seed=seed, uniform=1, normal=0)
    bpy.ops.object.mode_set(mode='OBJECT')


def dump_json(model_identifier, bbox, bboxes, materials, rotation, seed, path):
    data = {}
    data['label'] = model_identifier
    data['rotation'] = rotation
    data['bbox'] = bbox
    data['bboxes'] = bboxes
    data['materials'] = materials
    data['seed'] = seed

    with open(path + '.json', 'w') as json_file:
        json.dump(data, json_file)


def dump_csv(path, json_fname):
    with open(path, 'a', newline='') as fd:
        writer = csv.writer(fd)
        writer.writerow([json_fname])


def replace_materials(obj, materials):
    i = 0
    while i < len(obj.data.materials) and i < len(materials):
        obj.data.materials[i] = materials[i]
        i = i + 1


def setup_output(scene, fp, config):
    (resolution) = config
    scene.render.engine = 'CYCLES'
    # scene.cycles.device = 'GPU'
    scene.render.resolution_x = resolution
    scene.render.resolution_y = resolution
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_depth = "16"

    scene.use_nodes = True
    scene.view_layers["View Layer"].use_pass_vector = True
    scene.view_layers["View Layer"].use_pass_normal = True
    scene.view_layers["View Layer"].use_pass_diffuse_color = True

    tree = scene.node_tree
    links = tree.links
    for n in tree.nodes:
        tree.nodes.remove(n)

    # Create input render layer node.
    render_layers = tree.nodes.new('CompositorNodeRLayers')

    # Depth setup
    depth_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    depth_file_output.label = 'Depth Output'
    depth_file_output.base_path = fp
    depth_file_output.format.file_format = 'OPEN_EXR'
    links.new(render_layers.outputs['Depth'],
              depth_file_output.inputs['Image'])

    # Optical Flow setup
    flow_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    flow_file_output.label = 'Optical Flow Output'
    flow_file_output.base_path = fp
    flow_file_output.format.file_format = 'OPEN_EXR'
    links.new(render_layers.outputs['Vector'],
              flow_file_output.inputs['Image'])

    # Normal setup
    scale_normal = tree.nodes.new(type="CompositorNodeMixRGB")
    scale_normal.blend_type = 'MULTIPLY'
    scale_normal.inputs[2].default_value = (0.5, 0.5, 0.5, 1)
    links.new(render_layers.outputs['Normal'], scale_normal.inputs[1])

    bias_normal = tree.nodes.new(type="CompositorNodeMixRGB")
    bias_normal.blend_type = 'ADD'
    bias_normal.inputs[2].default_value = (0.5, 0.5, 0.5, 0)
    links.new(scale_normal.outputs[0], bias_normal.inputs[1])

    normal_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    normal_file_output.label = 'Normal Output'
    normal_file_output.base_path = fp
    normal_file_output.format.file_format = 'OPEN_EXR'
    links.new(bias_normal.outputs[0], normal_file_output.inputs[0])

    # Albedo setup
    albedo_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    albedo_file_output.label = 'Albedo Output'
    albedo_file_output.base_path = fp
    albedo_file_output.format.file_format = 'OPEN_EXR'
    links.new(render_layers.outputs['DiffCol'], albedo_file_output.inputs[0])

    return {"depth": depth_file_output, "flow": flow_file_output, "normal": normal_file_output, "albedo": albedo_file_output}


def setup_lights():
    # Make light just directional, disable shadows.
    light = bpy.data.lights['Light']
    light.type = 'SUN'
    light.cycles.cast_shadow = True
    light.energy = 2
    light.use_nodes = True
    light.node_tree.nodes['Emission'].inputs[1].default_value = 2

    # Add another light source so stuff facing away from light is not completely dark
    bpy.ops.object.light_add(type='SUN')
    light = bpy.data.lights['Sun']
    light.energy = 1
    light.cycles.cast_shadow = True
    light.use_nodes = True
    bpy.data.objects['Sun'].rotation_euler = bpy.data.objects['Light'].rotation_euler
    bpy.data.objects['Sun'].rotation_euler[0] += np.pi

    return [bpy.data.objects['Light'], bpy.data.objects['Sun']]


def create_camera_rig():
    # Scene stuff
    cam = bpy.context.scene.objects['Camera']
    cam.location = (0, 1, 0)
    cam.rotation_euler = (np.pi / 2, 0, np.pi)
    cam_constraint = cam.constraints.new(type='TRACK_TO')
    cam_constraint.track_axis = 'TRACK_NEGATIVE_Z'
    cam_constraint.up_axis = 'UP_Y'
    b_empty = parent_obj_to_camera(cam)
    cam_constraint.target = b_empty
    return cam, b_empty


def generate_materials(material_paths):
    from poliigon_converter import PMC_workflow as Load_Material_Helper
    lmh = Load_Material_Helper()
    materials = []
    print("Generating materials")
    for material_path in material_paths:
        old = blockPrint()
        _, material = lmh.build_material_from_set(bpy.context, material_path)
        enablePrint(old)
        print(material)
        materials.append(material)
    return materials


def setup_objects(materials, seed, ignore_items):
    # set material
    # randomize vertices
    # select vertices and edges
    all_edges, all_vertices = np.zeros((0, 2)), np.zeros((0, 3))
    mesh_data = {}

    for item in bpy.data.objects:
        if item in ignore_items:
            continue

        replace_materials(obj=item, materials=materials)
        randomize_vertices(obj=item, seed=seed)

        vertices, edges = get_vertices_and_edges(item)
        mesh_data[item] = (vertices, edges)
        if vertices.shape[0] == 0:
            continue
        all_vertices = np.concatenate([all_vertices, vertices], axis=0)
        all_edges = np.concatenate([all_edges, edges], axis=0)
    return all_vertices, all_edges, mesh_data


def render_scene(scene, cameraRig, camera, baseDir, numViews, output_nodes, model, seed):
    model_identifier, allVertices, allEdges, _, materials = model
    views_x, views_y, views_z = numViews
    stepsize_x, stepsize_y, stepsize_z = - \
        170 // views_x, 360 // views_y, 360 // views_z

    train_csv = os.path.join(baseDir, "train.csv")
    test_csv = os.path.join(baseDir, "test.csv")

    print("Rendering %s" % (model_identifier))
    index = 0
    for angle_x in range(85, -85, stepsize_x):
        rad_x = radians(angle_x)
        cameraRig.rotation_euler[0] = rad_x
        for angle_y in range(0, 360, stepsize_y):
            rad_y = radians(angle_y)
            cameraRig.rotation_euler[1] = rad_y
            for angle_z in range(0, 360, stepsize_z):
                rad_z = radians(angle_z)
                cameraRig.rotation_euler[2] = rad_z

                fname = model_identifier + "_%04d" % (index)
                scene.render.filepath = os.path.join(
                    baseDir, fname + "_render")
                for output_node in output_nodes:
                    output_nodes[output_node].file_slots[0].path = fname + "_" + output_node

                bbox, bboxes = get_camera_BBox(camera, scene, model)
                material_names = list(map(lambda material: material.name, materials))

                dump_json(model_identifier, bbox, bboxes, material_names, (angle_x, angle_y, angle_z), seed, os.path.join(baseDir, fname))
                dump_csv(test_csv if index % 3 == 0 else train_csv, fname + ".json")

                print("Rotation X:(%d, %2.2f), Y:(%d, %2.2f), Z:(%d, %2.2f). BBox: %s. Vertices: %d. Edges: %d" %
                      (angle_x, rad_x, angle_y, rad_y, angle_z, rad_z, bbox, len(allVertices), len(allEdges)))

                old = blockPrint()
                bpy.ops.render.render(write_still=True)
                enablePrint(old)

                for output_node in output_nodes:
                    remove_frame_number(os.path.join(
                        output_nodes[output_node].base_path, output_nodes[output_node].file_slots[0].path))

                index = index + 1


if __name__ == "__main__":
    ARGS = getArgs()

    OUTPUT_PATH = os.path.join(current_script_path, ARGS.output_folder)
    OUTPUT_NODES = setup_output(bpy.context.scene, fp=OUTPUT_PATH, config=(ARGS.resolution))

    old = blockPrint()
    bpy.data.objects['Cube'].select_set(state=True)
    bpy.ops.object.delete()
    bpy.ops.import_scene.obj(filepath=ARGS.obj)
    enablePrint(old)
    print("Imported %s" % (ARGS.obj))

    LIGHTS = setup_lights()
    CAMERA, CAMERA_RIG = create_camera_rig()

    MATERIAL_PATHS = list(map(lambda material_path: os.path.join(
        current_script_path, material_path), ARGS.material))
    MATERIALS = generate_materials(MATERIAL_PATHS)
    SEED = ARGS.seed
    ALL_VERTICES, ALL_EDGES, MESH_DATA = setup_objects(
        materials=MATERIALS, seed=SEED, ignore_items=[CAMERA, CAMERA_RIG] + LIGHTS)
    OUTPUT_NAME = ARGS.output_name

    t1 = time.time()

    render_scene(scene=bpy.context.scene, cameraRig=CAMERA_RIG, camera=CAMERA, baseDir=OUTPUT_PATH,
                 numViews=(ARGS.views_x, ARGS.views_y,
                           ARGS.views_z), output_nodes=OUTPUT_NODES,
                 model=(OUTPUT_NAME, ALL_VERTICES, ALL_EDGES, MESH_DATA, MATERIALS), seed=SEED)

    t2 = time.time()
    print(t2 - t1)