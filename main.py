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




import argparse, sys, os
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

current_script_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current_script_path)

from poliigon_converter import PMC_workflow as Load_Material_Helper

def getArgs():
    parser = argparse.ArgumentParser(description='Renders given obj file by rotation a camera around it.')
    # Views for the 3 euler angles
    parser.add_argument('--views_x', type=int, default=30)
    parser.add_argument('--views_y', type=int, default=30)
    parser.add_argument('--views_z', type=int, default=30)

    parser.add_argument('obj', type=str,
                        help='Path to the obj file to be rendered.')
    parser.add_argument('--output_folder', type=str, default='tmp',
                        help='The path the output will be dumped to.')
    parser.add_argument('--color_depth', type=str, default='8',
                        help='Number of bit per channel used for output. Either 8 or 16.')
    parser.add_argument('--material', type=str,
                        help='Material name. Check README.md')
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

def cleanup_initial_scene():
    bpy.data.objects['Cube'].select_set(state=True)
    bpy.ops.object.delete()
    bpy.data.objects['Camera'].select_set(state=True)
    bpy.ops.object.delete()

def generate_cameras(scene):
    top_camera_data = bpy.data.cameras.new(name="top")
    top_camera = bpy.data.objects.new(name="top", object_data=top_camera_data)
    top_camera.location = (0, 0, 2.5)
    top_camera.rotation_euler = (0, 0, 0)

    bot_camera_data = bpy.data.cameras.new(name="bot")
    bot_camera = bpy.data.objects.new(name="bot", object_data=bot_camera_data)
    bot_camera.location = (0, 0, -2.5)
    bot_camera.rotation_euler = (3.14, 0, 0)

    front_camera_data = bpy.data.cameras.new(name="front")
    front_camera = bpy.data.objects.new(name="front", object_data=front_camera_data)
    front_camera.location = (0, 2.5, 0)
    front_camera.rotation_euler = (1.57, 0, 3.14)

    rear_camera_data = bpy.data.cameras.new(name="rear")
    rear_camera = bpy.data.objects.new(name="rear", object_data=rear_camera_data)
    rear_camera.location = (0, -2.5, 0)
    rear_camera.rotation_euler = (1.57, 0, 0)

    side1_camera_data = bpy.data.cameras.new(name="side1")
    side1_camera = bpy.data.objects.new(name="side1", object_data=side1_camera_data)
    side1_camera.location = (2.5, 0, 0)
    side1_camera.rotation_euler = (1.57, 0, 1.57)

    side2_camera_data = bpy.data.cameras.new(name="side2")
    side2_camera = bpy.data.objects.new(name="side2", object_data=side2_camera_data)
    side2_camera.location = (-2.5, 0, 0)
    side2_camera.rotation_euler = (1.57, 0, -1.57)
    
    scene.collection.objects.link(top_camera)
    scene.collection.objects.link(bot_camera)
    scene.collection.objects.link(front_camera)
    scene.collection.objects.link(rear_camera)
    scene.collection.objects.link(side1_camera)
    scene.collection.objects.link(side2_camera)

def generate_lights(scene):
    light_data = bpy.data.lights.new(name="light", type='SUN')
    light_data.energy = 30
    light_object = bpy.data.objects.new(name="light", object_data=light_data)
    light_object.rotation_euler = (3.14, 0, 0)

    scene.collection.objects.link(light_object)

def edit_context_objects(context):
    scene = context.window.scene

    lmh = Load_Material_Helper()
    set_path = os.path.join(current_script_path, material_path)
    status, poliigon_material = lmh.build_material_from_set(context, set_path)

    for object in scene.objects:
        if object.type in ['CAMERA', 'LIGHT']:
            continue
        object.select_set(state=True)
        context.view_layer.objects.active = object

        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.remove_doubles()
        bpy.ops.object.mode_set(mode='OBJECT')

        bpy.ops.object.modifier_add(type='EDGE_SPLIT')
        context.object.modifiers["EdgeSplit"].split_angle = 1.32645
        bpy.ops.object.modifier_apply(modifier="EdgeSplit")

        bpy.ops.mesh.uv_texture_add()

        apply_poliigon_material(object, poliigon_material)

def apply_poliigon_material(obj, poliigon_material):
    obj.data.materials.clear()
    obj.data.materials.append(poliigon_material)

def get_bbox(scene):
    allEdges, allVertices = np.zeros((0, 2)), np.zeros((0, 3))
    meshesDict = {}
    for item in scene.objects:
        if item.type in ['CAMERA', 'LIGHT']:
            continue

        vertices, edges = getObjVerticesAndEdges(item)
        meshesDict[item.name] = (vertices, edges)
        if vertices.shape[0] == 0:
            continue
        allVertices = np.concatenate([allVertices, vertices], axis=0)
        allEdges = np.concatenate([allEdges, edges], axis=0)
    return np.min(allVertices, axis=0), np.max(allVertices, axis=0)

def getObjVerticesAndEdges(obj):
    vertices = np.array([list((obj.matrix_world @ v.co)) for v in obj.data.vertices])
    edges = np.array([list(i.vertices) for i in obj.data.edges])
    return vertices, edges

def getVisibleObjVerticesAndEdges(cam, scene, obj):
    obj = DeselectEdgesAndPolygons(obj)
    obj = select_visible_vertices(cam, scene, obj)

    mapVertices = [0] * len(obj.data.vertices)
    currentVertices = 0
    filteredVertices = []

    for i, vertex in enumerate(obj.data.vertices):
        if not vertex.select:
            continue
        mapVertices[i] = currentVertices
        filteredVertices.append(vertex)
        currentVertices += 1
    vertices = np.array([list((obj.matrix_world @ v.co)) for v in filteredVertices])

    edges = []
    for i, edge in enumerate(obj.data.edges):
        if not edge.select and (obj.data.vertices[edge.vertices[0]].select and obj.data.vertices[edge.vertices[1]].select):
            new_v1, new_v2 = mapVertices[edge.vertices[0]], mapVertices[edge.vertices[1]]
            edges.append((new_v1, new_v2))

    edges = np.array(edges)
    return vertices, edges

def computeBBoxDistances(thisVertices, MinBBox, MaxBBox):
    minDistances = thisVertices - MinBBox
    maxDistances = MaxBBox - thisVertices
    res = np.concatenate([minDistances, maxDistances], axis=1)
    return res

def DeselectEdgesAndPolygons( obj ):
    for p in obj.data.polygons:
        p.select = False
    for e in obj.data.edges:
        e.select = False
    return obj

def BVHTreeAndVerticesInWorldFromObj( obj ):
    mWorld = obj.matrix_world
    vertsInWorld = [mWorld @ v.co for v in obj.data.vertices]
    bvh = BVHTree.FromPolygons( vertsInWorld, [p.vertices for p in obj.data.polygons] )
    return bvh, vertsInWorld

def select_visible_vertices(cam, scene, obj):
    limit = 0.0001
    bvh, vertices = BVHTreeAndVerticesInWorldFromObj(obj)
    for i, v in enumerate(vertices):
        co2D = world_to_camera_view(scene, cam, v)
        obj.data.vertices[i].select = False
        if 0.0 <= co2D.x <= 1.0 and 0.0 <= co2D.y <= 1.0:
            location, normal, index, distance = bvh.ray_cast(cam.location, (v - cam.location).normalized())
            if location and (v - location).length < limit:
                obj.data.vertices[i].select = True
    return obj

def getDistancesToBBox(cam, scene, BBox):
    MinBBox, MaxBBox = BBox
    distancesDict = {}
    meshesDict = {}

    allEdges, allVertices = np.zeros((0, 2)), np.zeros((0, 3))
    for item in scene.objects:
        if item.type in ["CAMERA", "LIGHT"]:
            continue
        vertices, edges = getVisibleObjVerticesAndEdges(cam, scene, item)
        if len(vertices) == 0 or len(edges) == 0:
            continue
        allVertices = np.concatenate([allVertices, vertices], axis=0)
        allEdges = np.concatenate([allEdges, edges], axis=0)
    return allVertices, allEdges

def render_scene(baseDir, outputs, scene):
    scene.render.image_settings.file_format = 'PNG'
    cams = [c for c in scene.objects if c.type == 'CAMERA']
    bbox = get_bbox(scene)

    for c in cams:
        scene.camera = c               
        dg = bpy.context.evaluated_depsgraph_get()
        dg.update()

        print("Render", model_path, scene.name, c.name)
        scene.render.filepath = os.path.join(current_script_path, output_path, model_identifier + "_" + c.name)
        outputs["depth"].file_slots[0].path = scene.render.filepath + "_depth.exr"

        modelview_matrix = c.matrix_world
        projection_matrix = c.calc_matrix_camera(
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

        vertices, edges = getDistancesToBBox(c, scene, bbox)

        pklFile = open(scene.render.filepath + '.pkl', "wb")
        transformedVertices = np.zeros(vertices.shape)
        idx = 0
        for vertex in vertices:
            vertex = projection_matrix @ inv_modelview_matrix @ Vector((vertex[0], vertex[1], vertex[2], 1))
            vertex /= vertex.w
            transformedVertices[idx, :] = vertex[:-1]
            idx += 1
        pickle.dump(transformedVertices, pklFile)
        pickle.dump(edges.astype(np.int), pklFile)
        pklFile.close()

        old = blockPrint()
        bpy.ops.render.render(write_still=True)
        enablePrint(old)

def setup_blener():
    bpy.context.scene.use_nodes = True
    tree = bpy.context.scene.node_tree
    links = tree.links

    bpy.context.scene.render.engine = 'BLENDER_EEVEE'

    bpy.types.RenderLayer.use_pass_normal = True
    bpy.types.RenderLayer.use_pass_color = True
    bpy.context.scene.render.image_settings.file_format = "OPEN_EXR"
    bpy.context.scene.render.image_settings.color_depth = "16"

    for n in tree.nodes:
        tree.nodes.remove(n)

    render_layers = tree.nodes.new('CompositorNodeRLayers')

    depth_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    depth_file_output.label = 'Depth Output'
    links.new(render_layers.outputs['Depth'], depth_file_output.inputs[0])

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
    links.new(bias_normal.outputs[0], normal_file_output.inputs[0])

    albedo_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    albedo_file_output.label = 'Albedo Output'
    links.new(render_layers.outputs['DiffCol'], albedo_file_output.inputs[0])

    return depth_file_output

if __name__ == "__main__":
    args = getArgs()

    depth_file_output = setup_blener()
    depth_file_output.base_path = ""

    model_path = args.obj
    output_path = args.output_folder
    material_path = args.material

    context = bpy.context
    scene = context.window.scene

    cleanup_initial_scene()
    generate_cameras(scene)
    generate_lights(scene)

    bpy.ops.import_scene.obj(filepath=model_path)

    edit_context_objects(context)

    # Scene stuff
    scene.render.resolution_x = 600
    scene.render.resolution_y = 600
    scene.render.resolution_percentage = 100

    model_identifier = os.path.split(os.path.split(args.obj)[0])[1]
    fp = os.path.join(args.output_folder)
    if not os.path.exists(fp):
        os.makedirs(fp)

    light_data = bpy.data.lights.new(name="additional_light", type='POINT')
    light_data.cycles.cast_shadow = True
    light_data.use_nodes = True
    light_data.node_tree.nodes['Emission'].inputs[1].default_value = np.random.randint(30)
    light_object = bpy.data.objects.new(name="additional_light", object_data=light_data)

    bpy.context.collection.objects.link(light_object)
    light_object.location = (np.random.randint(2), np.random.randint(2), np.random.randint(2))

    render_scene(baseDir=fp, outputs={"depth": depth_file_output}, scene=scene)
