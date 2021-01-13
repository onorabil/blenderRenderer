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
import bmesh
from bpy_extras.object_utils import world_to_camera_view
from mathutils import Vector
from mathutils.bvhtree import BVHTree
import time
import pickle
from typing import List
# HARDCODED STUFF


current_script_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current_script_path)


from poliigon_converter import PMC_workflow as Load_Material_Helper


def getArgs():
    parser = argparse.ArgumentParser(
        description='Renders given obj file by rotation a camera around it.')
    # Views for the 3 euler angles
    parser.add_argument('--views_x', type=int, default=30)
    parser.add_argument('--views_y', type=int, default=30)
    parser.add_argument('--views_z', type=int, default=30)

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
    bpy.ops.transform.vertex_random(offset=0.0025, seed=seed, uniform=1, normal=0)
    bpy.ops.object.mode_set(mode='OBJECT')


def setup_output(scene, fp):
    scene.render.engine = 'CYCLES'
    scene.render.resolution_x = 600
    scene.render.resolution_y = 600
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
    links.new(render_layers.outputs['Depth'], depth_file_output.inputs['Image'])

    # Optical Flow setup
    # Link the movement vector to the image output, movement will be encoded in the rgba
    flow_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    flow_file_output.label = 'Optical Flow Output'
    flow_file_output.base_path = fp
    flow_file_output.format.file_format = 'OPEN_EXR'
    links.new(render_layers.outputs['Vector'], flow_file_output.inputs['Image'])

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

    albedo_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    albedo_file_output.label = 'Albedo Output'
    albedo_file_output.base_path = fp
    albedo_file_output.format.file_format = 'OPEN_EXR'
    links.new(render_layers.outputs['DiffCol'], albedo_file_output.inputs[0])

    return {"depth": depth_file_output, "flow": flow_file_output, "normal": normal_file_output, "albedo": albedo_file_output}


def dump_pkl(scene, allVertices, allEdges):
    dg = bpy.context.evaluated_depsgraph_get()

    modelview_matrix = scene.objects['Camera'].matrix_world
    projection_matrix = scene.objects['Camera'].calc_matrix_camera(
        dg,
        x=scene.render.resolution_x,
        y=scene.render.resolution_y,
        scale_x=scene.render.pixel_aspect_x,
        scale_y=scene.render.pixel_aspect_y,
    )

    inv_modelview_matrix = modelview_matrix.copy()
    inv_modelview_matrix.invert()
    inv_projection_matrix = projection_matrix.copy()
    inv_projection_matrix.invert()

    pklFile = open(scene.render.filepath + '.pkl', "wb")

    transformedVertices = np.zeros(allVertices.shape)

    idx = 0
    for vertex in allVertices:
        vertex = projection_matrix @ inv_modelview_matrix @ Vector(
            (vertex[0], vertex[1], vertex[2], 1))
        vertex /= vertex.w
        transformedVertices[idx, :] = vertex[:-1]
        idx += 1

    pickle.dump(transformedVertices, pklFile)
    pickle.dump(allEdges.astype(np.int), pklFile)
    pklFile.close()


def render_scene(scene, cameraRig, baseDir, numViews, output_nodes, model):
    model_identifier, allVertices, allEdges = model
    views_x, views_y, views_z = numViews
    stepsize_x, stepsize_y, stepsize_z = 360 // views_x, 360 // views_y, 360 // views_z

    for i in range(views_x):
        angle_x, rad_x = stepsize_x * i, radians(stepsize_x * i)
        cameraRig.rotation_euler[0] = rad_x
        for j in range(views_y):
            angle_y, rad_y = stepsize_y * j, radians(stepsize_y * j)
            cameraRig.rotation_euler[1] = rad_y
            for k in range(views_z):
                angle_z, rad_z = stepsize_z * k, radians(stepsize_z * k)
                cameraRig.rotation_euler[2] = rad_z

                fname = model_identifier + "_%d_%d_%d_%d" % (SEED, angle_x, angle_y, angle_z)
                scene.render.filepath = os.path.join(baseDir, fname)
                for output_node in output_nodes:
                    output_nodes[output_node].file_slots[0].path = fname + "_" + output_node

                dump_pkl(scene, allVertices, allEdges)

                print("Rotation. X:(%d, %2.2f), Y:(%d, %2.2f), Z:(%d, %2.2f). Vertices: %d. Edges: %d" %
                      (angle_x, rad_x, angle_y, rad_y, angle_z, rad_z, len(allVertices), len(allEdges)))

                old = blockPrint()
                bpy.ops.render.render(write_still=True)
                enablePrint(old)


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
    light2 = bpy.data.lights['Sun']
    light2.energy = 1
    light2.cycles.cast_shadow = True
    light2.use_nodes = True
    bpy.data.objects['Sun'].rotation_euler = bpy.data.objects['Light'].rotation_euler
    bpy.data.objects['Sun'].rotation_euler = (3.14, 0, 0)

    light_data = bpy.data.lights.new(name="additional_light", type='POINT')
    light_data.cycles.cast_shadow = True
    light_data.use_nodes = True
    light_data.node_tree.nodes['Emission'].inputs[1].default_value = np.random.randint(
        2)
    light_object = bpy.data.objects.new(
        name="additional_light", object_data=light_data)
    bpy.context.collection.objects.link(light_object)
    light_object.location = (np.random.randint(
        2), np.random.randint(2), np.random.randint(2))

    return [bpy.data.objects['Light'], bpy.data.objects['Sun'],  bpy.data.objects['additional_light']]


def create_camera_rig():
    # Scene stuff
    cam = bpy.context.scene.objects['Camera']
    cam.location = (0, 1, 0.6)
    cam_constraint = cam.constraints.new(type='TRACK_TO')
    cam_constraint.track_axis = 'TRACK_NEGATIVE_Z'
    cam_constraint.up_axis = 'UP_Y'
    b_empty = parent_obj_to_camera(cam)
    cam_constraint.target = b_empty
    return cam, b_empty


def generate_materials(material_paths: List[str]):
    lmh = Load_Material_Helper()
    materials = []
    for material_path in material_paths:
        _, material = lmh.build_material_from_set(bpy.context, material_path)
        materials.append(material)
    return materials


def replace_materials(obj, materials):
    i = 0
    while i < len(obj.data.materials) and i < len(materials):
        obj.data.materials[i] = materials[i]
        i = i + 1


def setup_models(materials, seed, ignore_items):
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
    return all_vertices, all_edges


if __name__ == "__main__":
    ARGS = getArgs()
    OUTPUT_PATH = os.path.join(current_script_path, ARGS.output_folder)

    OUTPUT_NODES = setup_output(bpy.context.scene, fp=OUTPUT_PATH)

    bpy.data.objects['Cube'].select_set(state=True)
    bpy.ops.object.delete()
    bpy.ops.import_scene.obj(filepath=ARGS.obj)

    LIGHTS = setup_lights()
    CAMERA, CAMERA_RIG = create_camera_rig()

    MATERIAL_PATHS = list(map(lambda material_path: os.path.join(current_script_path, material_path), ARGS.material))
    MATERIALS = generate_materials(MATERIAL_PATHS)
    SEED = ARGS.seed
    ALL_VERTICES, ALL_EDGES = setup_models(materials=MATERIALS, seed=SEED, ignore_items=[CAMERA, CAMERA_RIG] + LIGHTS)
    OUTPUT_NAME = ARGS.output_name

    render_scene(scene=bpy.context.scene, cameraRig=CAMERA_RIG, baseDir=OUTPUT_PATH, 
                numViews=(ARGS.views_x, ARGS.views_y, ARGS.views_z), output_nodes=OUTPUT_NODES, 
                model=(OUTPUT_NAME, ALL_VERTICES, ALL_EDGES))
