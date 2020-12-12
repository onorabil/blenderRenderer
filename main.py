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

# HARDCODED STUFF


current_script_path = os.path.dirname(os.path.realpath(__file__))
sys.path.append(current_script_path)


from poliigon_converter import PMC_workflow as Load_Material_Helper

# from Mihlib import *

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

# Disable
def blockPrint():
    open(os.devnull, 'a').close()
    old = os.dup(1)
    sys.stdout.flush()
    os.close(1)
    os.open(os.devnull, os.O_WRONLY)
    return old

# Restore
def enablePrint(old):
    os.close(1)
    os.dup(old)
    os.close(old)

def parent_obj_to_camera(b_camera):
    origin = (0, 0, 0)
    b_empty = bpy.data.objects.new("Empty", None)
    b_empty.location = origin
    b_camera.parent = b_empty  # setup parenting

    scn = bpy.context.scene
    ## scn.objects.link(b_empty)
    bpy.context.collection.objects.link(b_empty)
    bpy.context.view_layer.objects.active = b_empty
    #scn.objects.active = b_empty
    #scn.update()
    dg = bpy.context.evaluated_depsgraph_get()
    dg.update()
    return b_empty


def getObjVerticesAndEdges(obj):
    vertices = np.array([list((obj.matrix_world @ v.co)) for v in obj.data.vertices])
    edges = np.array([list(i.vertices) for i in obj.data.edges])
    #print('vertices')
    #print(vertices)
    #print('edges')
    #print(edges)
    return vertices, edges


def getVisibleObjVerticesAndEdges(scene, obj):
    obj = DeselectEdgesAndPolygons(obj)
    obj = select_visible_vertices(scene, obj)

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
        # if not edge.select or not obj.data.vertices[edge[0]].select or not obj.data.vertices[edge[1]].select:
        #     continue
        # print(obj.data.vertices[edge[0]].select)
        # print('e0', edge.vertices[0])
        #for prop in edge:
        #    print(prop)
        # print('e1', edge.vertices[1])
        if not edge.select and (obj.data.vertices[edge.vertices[0]].select and obj.data.vertices[edge.vertices[1]].select):
            #continue
            new_v1, new_v2 = mapVertices[edge.vertices[0]], mapVertices[edge.vertices[1]]
            edges.append((new_v1, new_v2))

    edges = np.array(edges)
    return vertices, edges

def computeBBoxDistances(thisVertices, MinBBox, MaxBBox):
    minDistances = thisVertices - MinBBox
    maxDistances = MaxBBox - thisVertices
    res = np.concatenate([minDistances, maxDistances], axis=1)
    return res

# Deselect mesh polygons and vertices
def DeselectEdgesAndPolygons( obj ):
    for p in obj.data.polygons:
        p.select = False
    for e in obj.data.edges:
        e.select = False
    return obj


# Create a BVH tree and return bvh and vertices in world coordinates
def BVHTreeAndVerticesInWorldFromObj( obj ):
    mWorld = obj.matrix_world
    vertsInWorld = [mWorld @ v.co for v in obj.data.vertices]
    bvh = BVHTree.FromPolygons( vertsInWorld, [p.vertices for p in obj.data.polygons] )
    return bvh, vertsInWorld


def select_visible_vertices(scene, obj):
    # Threshold to test if ray cast corresponds to the original vertex
    limit = 0.0001
    # In world coordinates, get a bvh tree and vertices
    # sce = context.scene
    camera = scene.objects['Empty'].children[0]
    #camera = scene.objects['Camera']
    print(camera)

    bvh, vertices = BVHTreeAndVerticesInWorldFromObj( obj )
    for i, v in enumerate( vertices ):
        # Get the 2D projection of the vertex
        co2D = world_to_camera_view( scene, camera, v )

        # By default, deselect it
        obj.data.vertices[i].select = False

        # If inside the camera view
        if 0.0 <= co2D.x <= 1.0 and 0.0 <= co2D.y <= 1.0:
            # Try a ray cast, in order to test the vertex visibility from the camera
            location, normal, index, distance = bvh.ray_cast( cam.location, (v - cam.location).normalized() )
            # If the ray hits something and if this hit is close to the vertex, we assume this is the vertex
            if location and (v - location).length < limit:
                obj.data.vertices[i].select = True
    return obj

def getDistancesToBBox(cam, scene, BBox):
    MinBBox, MaxBBox = BBox
    distancesDict = {}
    meshesDict = {}

    allEdges, allVertices = np.zeros((0, 2)), np.zeros((0, 3))
    for item in bpy.data.objects:
        if item.name in ["Camera", "Empty", "Light", "Sun", "additional_light"]:
            continue
        #need vertices selected here
        # WTF ???
        vertices, edges = getVisibleObjVerticesAndEdges(scene, item)
        print('selected vertices', len(vertices))
        print('selected edges', len(edges))
        if len(vertices) == 0 or len(edges) == 0:
            continue
        # assert len(vertices) > 0 and len(edges) > 0
        # vertices, edges = getObjVerticesAndEdges(item)
        allVertices = np.concatenate([allVertices, vertices], axis=0)
        allEdges = np.concatenate([allEdges, edges], axis=0)
        # MinBBox, MaxBBox = np.min(allVertices, axis=0), np.max(allVertices, axis=0)
    return allVertices, allEdges

def render_scene(camera, baseDir, numViews, outputs, BBox):
    scene = bpy.context.scene
    scene.render.image_settings.file_format = 'PNG'
    views_x, views_y, views_z = numViews
    stepsize_x, stepsize_y, stepsize_z = 360 // views_x, 360 // views_y, 360 // views_z

    # print(list(scene.objects))
    # return

    # TODO
    cameraWTF = scene.objects['Camera']

    old = blockPrint()
    bpy.ops.render.render(write_still=False)
    enablePrint(old)

    for i in range(views_x):
        angle_x, rad_x = stepsize_x * i, radians(stepsize_x * i)
        camera.rotation_euler[0] = rad_x
        for j in range(views_y):
            angle_y, rad_y = stepsize_y * j, radians(stepsize_y * j)
            camera.rotation_euler[1] = rad_y
            for k in range(views_z):
                angle_z, rad_z = stepsize_z * k, radians(stepsize_z * k)
                camera.rotation_euler[2] = rad_z
                # scene.update()
                dg = bpy.context.evaluated_depsgraph_get()
                dg.update()
                #bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)
                time.sleep(3)
                scene.render.filepath = os.path.join(fp, "render_%d_%d_%d" % (angle_x, angle_y, angle_z))
                outputs["depth"].file_slots[0].path = scene.render.filepath + "_depth.exr"
                # normal_file_output.file_slots[0].path = scene.render.filepath + "_normal.exr"
                # albedo_file_output.file_slots[0].path = scene.render.filepath + "_albedo.exr"

                modelview_matrix = cameraWTF.matrix_world
                projection_matrix = cameraWTF.calc_matrix_camera(
                    dg,
                    x=scene.render.resolution_x,
                    y=scene.render.resolution_y,
                    scale_x=scene.render.pixel_aspect_x,
                    scale_y=scene.render.pixel_aspect_y,
                )

                # TODO
                inv_modelview_matrix = modelview_matrix.copy()
                inv_modelview_matrix.invert()
                inv_projection_matrix = projection_matrix.copy()
                inv_projection_matrix.invert()

                # print(modelview_matrix, projection_matrix)

                # TODO make an output interface
                pklFile = open(scene.render.filepath + '.pkl', "wb")
                # objFile = open(scene.render.filepath + '.obj', "w")

                transformedVertices = np.zeros(allVertices.shape)

                # objFile.write('# vertices\n')
                idx = 0
                for vertex in allVertices:
                    vertex = projection_matrix @ inv_modelview_matrix @ Vector((vertex[0], vertex[1], vertex[2], 1))
                    vertex /= vertex.w
                    transformedVertices[idx, :] = vertex[:-1]
                    # objFile.write('v {0:.7f} {1:.7f} {2:.7f}\n'.format(vertex[0], vertex[1], vertex[2]))
                    idx += 1

                # objFile.write('# faces\n')

                pickle.dump(transformedVertices, pklFile)
                pickle.dump(allEdges.astype(np.int), pklFile)
                # objFile.close()
                pklFile.close()
                # TODO

                vertices, edges = getDistancesToBBox(camera, scene, BBox)
                print("Rotation. X:(%d, %2.2f), Y:(%d, %2.2f), Z:(%d, %2.2f). Vertices: %d. Edges: %d" % \
                    (angle_x, rad_x, angle_y, rad_y, angle_z, rad_z, len(vertices), len(edges)))

                old = blockPrint()
                bpy.ops.render.render(write_still=True)  # render still
                enablePrint(old)

if __name__ == "__main__":
    args = getArgs()
    # Set up rendering of depth map.
    bpy.context.scene.use_nodes = True
    tree = bpy.context.scene.node_tree
    links = tree.links

    # material path
    MATERIAL_NAME = args.material #'TilesMarbleSageGreenBrickBondHoned001_3K'
    MATERIAL_PATH = os.path.join(current_script_path, 'poliigon_material_samples', MATERIAL_NAME)

    # render w/ cycles
    bpy.context.scene.render.engine = 'BLENDER_EEVEE'

    # Add passes for additionally dumping albedo and normals.
    #bpy.context.scene.render.layers["RenderLayer"].use_pass_normal = True
    #bpy.context.scene.render.layers["RenderLayer"].use_pass_color = True
    bpy.types.RenderLayer.use_pass_normal = True
    bpy.types.RenderLayer.use_pass_color = True
    bpy.context.scene.render.image_settings.file_format = "OPEN_EXR"
    bpy.context.scene.render.image_settings.color_depth = "16"

    # Clear default nodes
    for n in tree.nodes:
        tree.nodes.remove(n)

    # Create input render layer node.
    render_layers = tree.nodes.new('CompositorNodeRLayers')

    # Depth setup
    depth_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    depth_file_output.label = 'Depth Output'
    links.new(render_layers.outputs['Depth'], depth_file_output.inputs[0])

    scale_normal = tree.nodes.new(type="CompositorNodeMixRGB")
    scale_normal.blend_type = 'MULTIPLY'
    # scale_normal.use_alpha = True
    scale_normal.inputs[2].default_value = (0.5, 0.5, 0.5, 1)
    links.new(render_layers.outputs['Normal'], scale_normal.inputs[1])

    bias_normal = tree.nodes.new(type="CompositorNodeMixRGB")
    bias_normal.blend_type = 'ADD'
    # bias_normal.use_alpha = True
    bias_normal.inputs[2].default_value = (0.5, 0.5, 0.5, 0)
    links.new(scale_normal.outputs[0], bias_normal.inputs[1])

    normal_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    normal_file_output.label = 'Normal Output'
    links.new(bias_normal.outputs[0], normal_file_output.inputs[0])

    albedo_file_output = tree.nodes.new(type="CompositorNodeOutputFile")
    albedo_file_output.label = 'Albedo Output'
    #for x in render_layers.outputs:
    #    print(x)
    #links.new(render_layers.outputs['Color'], albedo_file_output.inputs[0])
    links.new(render_layers.outputs['DiffCol'], albedo_file_output.inputs[0])

    # Delete default cube
    #bpy.data.objects['Cube'].select = True
    bpy.data.objects['Cube'].select_set(state=True)
    bpy.ops.object.delete()

    bpy.ops.import_scene.obj(filepath=args.obj)
    for object in bpy.context.scene.objects:
        if object.name in ['Camera', 'Light']:
            continue
        #bpy.context.scene.objects.active = object
        object.select_set(state=True)
        bpy.context.view_layer.objects.active = object
        print('sel o', bpy.context.selected_objects[0])
        #bpy.context.selected_objects(object)
        # "Remove doubles"
        bpy.ops.object.mode_set(mode='EDIT')
        bpy.ops.mesh.remove_doubles()
        bpy.ops.object.mode_set(mode='OBJECT')

        # "Edge split"
        bpy.ops.object.modifier_add(type='EDGE_SPLIT')
        bpy.context.object.modifiers["EdgeSplit"].split_angle = 1.32645
        bpy.ops.object.modifier_apply(modifier="EdgeSplit")

        # "Remesh"  for better texture rendering
        # bpy.ops.object.modifier_add(type='REMESH')
        # bpy.context.object.modifiers["Remesh"].mode = 'SMOOTH'
        # bpy.context.object.modifiers["Remesh"].octree_depth = 4
        # bpy.context.object.modifiers["Remesh"].scale = 0.99
        # bpy.context.object.modifiers["Remesh"].use_smooth_shade = True
        # bpy.ops.object.modifier_apply(modifier="Remesh")

        # add uv map
        #bpy.ops.uv.smart_project()
        bpy.ops.mesh.uv_texture_add()



    # Make light just directional, disable shadows.
    light = bpy.data.lights['Light']
    light.type = 'SUN'
    light.cycles.cast_shadow = True
    light.energy = 80  ######################################################## Do for the other lights
    light.use_nodes = True
    light.node_tree.nodes['Emission'].inputs[1].default_value = 20
    # Possibly disable specular shading:

    ## HERE
    ##light.use_specular = False

    # Add another light source so stuff facing away from light is not completely dark
    bpy.ops.object.light_add(type='SUN')
    light2 = bpy.data.lights['Sun']
    #light2.use_specular = False
    light2.cycles.cast_shadow = True
    light2.use_nodes = True
    ## light2.node_tree.nodes['Emission'].inputs[1].default_value = 10
    bpy.data.objects['Sun'].rotation_euler = bpy.data.objects['Light'].rotation_euler
    bpy.data.objects['Sun'].rotation_euler[0] += 180

    # Scene stuff
    scene = bpy.context.scene
    scene.render.resolution_x = 600
    scene.render.resolution_y = 600
    scene.render.resolution_percentage = 100
    ## scene.render.alpha_mode = 'TRANSPARENT'
    cam = scene.objects['Camera']
    cam.location = (0, 1, 0.6)
    cam_constraint = cam.constraints.new(type='TRACK_TO')
    cam_constraint.track_axis = 'TRACK_NEGATIVE_Z'
    cam_constraint.up_axis = 'UP_Y'
    b_empty = parent_obj_to_camera(cam)
    cam_constraint.target = b_empty

    # bvh, vertices = BVHTreeAndVerticesInWorldFromObj( bpy.data.objects["mesh1_mesh1-geometry"]  )
    # for v in vertices:
    #     co2D = world_to_camera_view( scene, scene.camera, v )


    # print(scene.camera.view_frame)
    # print(cam.view_frame)
    # print(b_empty.view_frame)

    model_identifier = os.path.split(os.path.split(args.obj)[0])[1]
    fp = os.path.join(args.output_folder)
    if not os.path.exists(fp):
        os.makedirs(fp)
    # # for output_node in [depth_file_output, normal_file_output, albedo_file_output]:
    #     # output_node.base_path = ''
    set_path = MATERIAL_PATH
    lmh = Load_Material_Helper()
    status, poliigon_material = lmh.build_material_from_set(bpy.context, set_path)
    #material_test = bpy.data.materials.get("RoadAsphaltWorn006_HIRES")

    depth_file_output.base_path = ""

    allEdges, allVertices = np.zeros((0, 2)), np.zeros((0, 3))
    meshesDict = {}
    for item in bpy.data.objects:
        if item.name in ["Camera", "Empty", "Light", "Sun", "additional_light"]:
            continue
        print(item.name)
        #assign material
        if item.data.materials:
            # assign to 1st material slot
            item.data.materials[0] = poliigon_material
        else:
            # no slots
            item.data.materials.append(mat)

        #need vertices selected here
        vertices, edges = getObjVerticesAndEdges(item)
        meshesDict[item.name] = (vertices, edges)
        if vertices.shape[0] == 0: # no vertices for whatever reason
            continue
        allVertices = np.concatenate([allVertices, vertices], axis=0)
        allEdges = np.concatenate([allEdges, edges], axis=0)
    MinBBox, MaxBBox = np.min(allVertices, axis=0), np.max(allVertices, axis=0)

    #     print('vertices')
    #     print(thisVertices)
    #     print('separate vertices')
    #     print('cm', modelview_matrix)
    #     print('pm', projection_matrix)
    #     for vertex in thisVertices:
    #         print(vertex)
    #         vertex_transformed = projection_matrix * modelview_matrix * Vector((vertex[0], vertex[1], vertex[2], 1))
    #         vertex_transformed /= vertex_transformed.w
    #         print(vertex_transformed)

    light_data = bpy.data.lights.new(name="additional_light", type='POINT')
    light_data.cycles.cast_shadow = True
    light_data.use_nodes = True
    light_data.node_tree.nodes['Emission'].inputs[1].default_value = np.random.randint(30)
    light_object = bpy.data.objects.new(name="additional_light", object_data=light_data)
    ## scene.objects.link(light_object)
    bpy.context.collection.objects.link(light_object)
    light_object.location = (np.random.randint(2), np.random.randint(2), np.random.randint(2))

    render_scene(camera=b_empty, baseDir=fp, numViews=(args.views_x, args.views_y, args.views_z),
                 outputs={"depth": depth_file_output}, BBox=(MinBBox, MaxBBox))
