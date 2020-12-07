import json
import os
import re

import bpy
import mathutils


# -----------------------------------------------------------------------------
# STATIC STRINGS (for regex matching)
# -----------------------------------------------------------------------------

# searches for e.g. the _2K_ in "sometext_2K_moretext" or "..._14K.png"
# negative lookahead is why the code is duplicated within the (?! )
SEARCH_SIZE=r"[-_ ]{1}[0-9]{1,3}[kK]{1}[-_ .]{1}(?!.*[-_ ]{1}[0-9]{1,3}[kK]{1}[-_ .]{1})"
# get HIRES from e.g. setname_GLOSS_HIRES.jpeg, negative lookahead
SEARCH_HIRES=r"(?i)[-_ ]{1}(HIRES)(?!.*[-_ ]{1}(HIRES)[.]{1})"

# determines if METALNESS or SPECULAR (not case sensitive) at end of filename
SPEC_WORKFLOW=r"(?i)SPECULAR[.]{1}[a-zA-Z]{3}(?!.*SPECULAR[.]{1}[a-zA-Z]{3})"
METAL_WORKFLOW=r"(?i)METALNESS[.]{1}[a-zA-Z]{3}(?!.*METALNESS[.]{1}[a-zA-Z]{3})"

# Detects if basepath has REFLECTION or GLOSS pass
GLOSS_REFLECT_PASS=r"(?i)[-_ ]{1}(GLOSS|REFLECTION|REFL)[-_ ]{1}"

# e.g. find material_NRM_ out of material_NRM_2K, or find
# material_NRM-2K- out of material_NRM-2K-METALNESS
MATCH_BEFORE_LAST_SEPARATOR=r"^(.*[-_ ])"

# find any VAR# within pass, to help prefer lowest variance type for given texture
# (consider implementing negative lookahead)
SEARCH_VAR = r"(?i)[-_ ]{1}var[0-9]{1,2}[-_ ]{1}"

# fallback search for preview, if not in preview folder
SEARCH_THUMB=r"(?i)[-_ ]{1}(PREVIEW|THUMB|THUMBNAIL|ICON)[-_ .]{1}"

# -----------------------------------------------------------------------------
# INTERNAL METHODS/CLASSES
# -----------------------------------------------------------------------------

class Load_Material_Helper():
    """
    Supports the building of materials and detecting of material sets

    While some functions are used to identify multiple material sets from a
    directory, the internally used variables and parameters are configured
    to be specific to a single material set
    """

    def __init__(self, use_ao=True, use_disp=True, use_sixteenbit=False,
                verbose=True, conform_uv=True, microdisp=False):
        self.engine = None # see below
        self.workflow = None # one of: METALNESS or SPECULAR
        self.material = None # material ID block once created
        self.setname = None # path to base set, but including size
        self.status = {} # for storing status such as errors or other info
        self.passes = self.pass_names()
        self.size = None # numeric size of pass, or HIRES
        self.setpath = None

        self.use_ao=use_ao
        self.use_disp=use_disp
        self.use_sixteenbit=use_sixteenbit
        self.conform_uv=conform_uv
        self.microdisp = microdisp

        # auto set workflow based on render engine and
        # if Principled BSDF in node types, and engine==Cycles, set "cycles_principled"
        # for now, just using:
        self.engine = "cycles_principled"
        # provide extra logging information
        self.verbose = True
        
        
    def build_material_from_set(self, context, set_path, dryrun=False):
        """
        Builds all materials given a file sets
        Returns status, material ID
        """
        print('set path WTF', set_path)
        verbose = True

        # note that: set_path has e.g. -2K or _10K etc at end, and nothing after
        set_path_presize = re.search(MATCH_BEFORE_LAST_SEPARATOR,
                            set_path).group(0)[:-1] # remove last "-_ "

        cmpsize = set_path[len(set_path_presize)+1:] # ie 4K of .._4K
        set_presize = os.path.basename(set_path_presize)
        #set_presize = set_path_presize
        print('set presize', set_presize)
        #dirname = os.path.dirname(set_path_presize)
        dirname = set_path
        print("DIRNAME", dirname)
        # clear existing workflow settings
        self.status = {}
        self.setpath = set_path
        self.setname = os.path.basename(set_path)
        self.workflow = None
        self.size = None
        self.passes = self.pass_names()
        self.material = None

        if verbose:
            print("\nPoliigon: MATERIAL BUILD PARAMETERS")
            print("\tSetname:",self.setname)
            print("\tSet path + size:",set_path)
            print("\tDetected size:"+str(cmpsize))

        # Find files with matching texture size and setpath
        # structure of matching:
        #        if listed file exists (failsafe, always should be via listdir)
        #        if the basename match the setname (with size chopped off)
        #        if the below match pattern exists (e.g. if unrelated files in folder, skip)
        #        if the size param, e.g. 2K matches, via comparing the STRING number
        #        OR if the size value is HIRES
        set_files = [file for file in os.listdir(dirname)
                    if (os.path.isfile(os.path.join(dirname,file))
                    and os.path.basename(file).startswith(set_presize))]
        """
        and ((re.search(SEARCH_SIZE,os.path.basename(file)) is not None
            and re.search(SEARCH_SIZE,os.path.basename(file)
            ).group(0)[1:-1]==cmpsize))
            or (re.search(SEARCH_HIRES,os.path.basename(file)) is not None
            and cmpsize=="HIRES"
            ))]
        """
        # pre-determine the workflow method, greedy towards METALNESS
        # but fallback to DIELECTRIC, unless only specular exists
        neutral_count = 0
        specular_count = 0

        for file in set_files:
            bf = os.path.basename(file)
            m = re.search(METAL_WORKFLOW, bf)
            if m:
                self.workflow = "METALNESS"
                break
            m = re.search(SPEC_WORKFLOW, bf)
            if not m:
                neutral_count+=1
            else:
                specular_count+=1
        if self.workflow!="METALNESS":
            if specular_count>0 and neutral_count==0:
                self.workflow = "SPECULAR"
                self.status["Specular workflow found"] = \
                        ["Download metalness workflow files instead"]
            else:
                self.workflow = "DIELECTRIC" # default, most common case

        if verbose:
            print("\tDetected workflow: {}".format(
                    str(self.workflow)))
            print("Poliigon: Printing all selected material files")
            print(set_files)

        # go file by file, matching passes where possible and matching workflow
        # Matching is greedy: assign first, and then re-assign if more fitting
        # match exists (e.g. when preferring VAR1 over VAR2)
        for file in sorted(set_files):
            matched_to_pass = False
            bf = os.path.basename(file)

            # match passes to loose pass names, e.g. COLOR and COL will both match
            for passtype in self.get_passes_loose_names():

                # skip invalid apss names
                if not hasattr(self.passes, passtype.upper()):
                    # shouldn't really ever occur
                    continue

                # pre-determined includes or excludes
                if not self.use_ao and passtype=="AO":
                    continue
                if not self.use_disp and passtype in ["DISPLACEMENT","DISP"]:
                    continue

                # do check for 16-bit variant
                # greedy include, pass if non 16-bit already set AND setting is off
                src = re.search(r"(?i)[-_ ]{1}"+passtype+r"[-_ ]{1}",bf)
                if not src:
                    src_16 = re.search(r"(?i)[-_ ]{1}"+passtype+r"16[-_ ]{1}",bf)
                    if not src_16:
                        # print("Pass skip, not in filename: "+passtype)
                        continue
                    elif getattr(self.passes, passtype.upper()) != None and \
                            not self.use_sixteenbit:
                        continue # ie pass already exists and 16bit not enabled

                # check matchingness to workflow type
                if self.workflow=="METALNESS" and re.search(SPEC_WORKFLOW, bf):
                    if verbose:print("\tSkipping file, not metal workflow: ",bf)
                    continue # skip any specular matches
                elif self.workflow=="SPECULAR" and re.search(METAL_WORKFLOW, bf):
                    if verbose:print("\tSkipping file, not specular workflow: ",bf)
                    continue
                elif passtype == "METALNESS" and \
                        passtype not in re.sub(METAL_WORKFLOW, "", bf):
                    if verbose:
                        print("\tSkipping file, metalness is for workflow not pass: ",bf)
                    continue # ie was matching metalness against workflow, not passname

                # scenario where 16 bit enabled, and already has filled pass slot
                # should choose to skip this non-16 bit pass (since src is ! None)
                if self.use_sixteenbit and src:
                    if getattr(self.passes, passtype.upper()) is not None:
                        continue

                # Prefer lowest var number, if there are any
                varn = re.search(SEARCH_VAR,bf)
                if varn:
                    present_pass = getattr(self.passes, passtype.upper())
                    if present_pass != None:
                        varn_current = re.search(SEARCH_VAR,bf)
                        varnint_current = int(varn_current.group(0)[4:-1])
                        varnint = int(varn.group(0)[4:-1])
                        if varnint_current >= varnint:
                            continue

                matched_to_pass = True
                # set path to that pass' file,
                # e.g. self.passes.AO = '/path/to/setname_AO.jpg'
                setattr(self.passes, passtype.upper(), os.path.join(dirname,file))

                # do size check from filename, looking for e.g. 2K
                m = re.search(SEARCH_SIZE,bf)
                hi = re.search(SEARCH_HIRES,bf)
                if m:
                    tmpsize = int(m.group(0)[1:-2]) # cut off the _ & k_
                    if self.size==None:
                        self.size = m.group(0)[1:-1]
                    else:
                        if tmpsize < int(self.size[:-1]):
                            self.size = m.group(0)[1:-1]
                elif hi:
                    if self.size==None:
                        self.size = hi.group(0)[1:]

            if matched_to_pass==False:
                if verbose: print("\tFile not matched to pass type: "+file)

        # Identify critical passes and what should create warnings/not auto
        # check for importing because such image pass is missing
        missing_critical = []
        if self.workflow=="METALNESS":
            if not self.passes.COLOR and not self.passes.ALPHAMASKED:
                missing_critical.append("Color")
            if not self.passes.METALNESS: missing_critical.append("Metalness")
            if not self.passes.NORMAL: missing_critical.append("Normal")
            if not self.passes.ROUGHNESS: missing_critical.append("Roughness")
        else:
            if not self.passes.COLOR and not self.passes.ALPHAMASKED:
                missing_critical.append("Color")
            if not self.passes.REFLECTION: missing_critical.append("Reflection")
            if not self.passes.GLOSS: missing_critical.append("Gloss")
            if not self.passes.NORMAL: missing_critical.append("Normal")

        # generate associated warnings
        if len(missing_critical)>0:
            self.status["Missing critical passes"]=[str(missing_critical)]
            if self.verbose:
                print("Poliigon: Missing critical passes: ",missing_critical)

        if not dryrun:
            self.build_material(context, files=set_files)
            #self.save_settings_to_props() # save workflow settings to material

        return self.status, self.material

    # generic function to create material from provided data
    def build_material(self, context, files=[], workflow=None, material=None):
        print("poliigon files:", files)
        if self.verbose: print("Poliigon: Building material")

        #load variables if provided
        if workflow != None:
            self.workflow = workflow

        # internally ensure workflow method exists
        if self.engine==None:
            self.status["ERROR"] = ["Workflow not yet set"]
            return
        elif hasattr(self,"build_"+self.engine)==False:
            self.status["ERROR"] = ["Workflow build does not exist:",
                                    "build_"+self.engine]
            return

        # create new or check if material exists
        if material == None:
            self.material = bpy.data.materials.new(self.build_name())
        else:
            if material not in bpy.data.materials:
                return {"ERROR","Material does not exist"}
            self.material = material

        # general settings
        self.material.use_fake_user = True
        self.material.use_nodes = True

        # setup and build material
        mat_config = getattr(self,"build_"+self.engine)()
        m_nodes = self.material.node_tree.nodes
        m_links = self.material.node_tree.links

        # clear existing nodes (if any), and add new ones
        for n in m_nodes:
            m_nodes.remove(n)

        for node_name, node_data in mat_config["nodes"].items():
            node = m_nodes.new(node_data["type_id"])
            node.select = False
            mat_config["nodes"][node_name]["datablock"] = node
            node.name = node_name
            node.label = node_name
            for key, value in node_data.items():
                if key not in {"type", "type_id", "datablock"}:
                    if hasattr(value, '__call__'):
                        value = value()
                    setattr(node, key, value)

        if mat_config["nodes"]["COLOR"]["datablock"]:
            # To make the diffuse color texture preview in cycles texture mode
            mat_config["nodes"]["COLOR"]["datablock"].select = True
            m_nodes.active = mat_config["nodes"]["COLOR"]["datablock"]

        # Linking
        for from_node, from_socket, to_node, to_socket in mat_config["links"]:
            m_links.new(
                mat_config["nodes"][from_node]["datablock"].outputs[from_socket],
                mat_config["nodes"][to_node]["datablock"].inputs[to_socket])

        # updating defaults
        for node, index, value in mat_config["defaults"]:
            try:
                mat_config["nodes"][node]["datablock"].inputs[index].default_value = value
            except:
                print("Poliigon: Error setting default node value: ",node, index, value)

        # Load available images
        for imgpass in self.get_passes():
            imgpath = getattr(self.passes, imgpass)
            if imgpass not in mat_config["nodes"]:
                if imgpass=="ALPHAMASKED" and imgpath != None:
                    image = bpy.data.images.load(imgpath)
                    image.name = os.path.basename(imgpath)
                    mat_config["nodes"]["COLOR"]["datablock"].image = image
                    mat_config["nodes"]["COLOR"]["datablock"].mute = False

                # Pass name MUST match name of an image node,
                # but have it fail silently. This would only
                # ever be an addon configuration error, not user.
                # raise ValueError("Missing node for image pass "+imgpass)
                elif self.verbose:
                    print("\tImage node {} not present in material".format(imgpass))
            elif imgpath == None:
                if mat_config["nodes"][imgpass]["datablock"].image:
                    print("\tImage pass {} not set, but node already assigned".format(
                        imgpass))
                    continue
                if self.verbose:print("\tImage pass {} not set".format(imgpass))
                mat_config["nodes"][imgpass]["datablock"].mute = True
            else:
                # prefer alphamasked over color
                if imgpass=="COLOR" and \
                    mat_config["nodes"]["COLOR"]["datablock"].image!=None: continue
                if imgpass=="MASK" and \
                    mat_config["nodes"]["ALPHA"]["datablock"].image!=None: continue
                # prefer alpha over mask
                image = bpy.data.images.load(imgpath)
                image.name = os.path.basename(imgpath)
                mat_config["nodes"][imgpass]["datablock"].image = image
                mat_config["nodes"][imgpass]["datablock"].mute = False # in case overrwite

        # additional rules/logic post base creation

        # created named ID property, for flagging manipulation nodes later
        mat_config["nodes"]["Mapping"]["datablock"]["main_map"] = True

        # disable sample as light to reduce noise
        self.material.cycles.sample_as_light = False


        # if SSS is present, assign low color value, otherwise delete
        if self.passes.SSS == None:
            m_nodes.remove(mat_config["nodes"]["SSS"]["datablock"])
        else:
            mat_config["nodes"]["Principled BSDF"]["datablock"].inputs[1].default_value = 0.005

        if self.workflow == "METALNESS":
            m_nodes.remove(mat_config["nodes"]["REFLECTION"]["datablock"])
            m_nodes.remove(mat_config["nodes"]["GLOSS"]["datablock"])
            m_nodes.remove(mat_config["nodes"]["Invert"]["datablock"])
            # make link from roughness node to roughness socket
            rough_node = mat_config["nodes"]["ROUGHNESS"]["datablock"]
            prin_node = mat_config["nodes"]["Principled BSDF"]["datablock"]
            m_links.new(rough_node.outputs[0],prin_node.inputs[7])

        elif self.workflow == "SPECULAR" or self.workflow == "DIELECTRIC":
            metal_node = mat_config["nodes"]["METALNESS"]["datablock"]
            m_nodes.remove(metal_node)
            rough_node = mat_config["nodes"]["ROUGHNESS"]["datablock"]
            m_nodes.remove(rough_node)

        map_node = mat_config["nodes"]["Mapping"]["datablock"]
        img = mat_config["nodes"]["COLOR"]["datablock"].image
        if img==None:
            img = mat_config["nodes"]["NORMAL"]["datablock"].image

        if self.conform_uv:
            # Could be made smarter in event the color node is missing,
            # and confirm based on another available pass
            if img and img.size[0] > 0 and img.size[1] > 0:
                ratio = img.size[1]/img.size[0] # height / width
                map_node.scale[0] = ratio
            else:
                if self.verbose:
                    print("Poliigon: No color/normal image, couldn't set conform to UV")

        # set alpha correctly
        if self.passes.ALPHAMASKED==None and self.passes.ALPHA==None:
            m_nodes.remove(mat_config["nodes"]["ALPHA"]["datablock"])
            m_nodes.remove(mat_config["nodes"]["ALPHA MIX"]["datablock"])
            m_nodes.remove(mat_config["nodes"]["Transparent BSDF"]["datablock"])
        elif self.passes.ALPHA==None or self.passes.ALPHAMASKED!=None:
            m_nodes.remove(mat_config["nodes"]["ALPHA"]["datablock"])

        if self.passes.ALPHAMASKED!=None:
            color_node = mat_config["nodes"]["COLOR"]["datablock"]
            amix_node = mat_config["nodes"]["ALPHA MIX"]["datablock"]
            m_links.new(color_node.outputs[1],amix_node.inputs[0])
            princ_node = mat_config["nodes"]["Principled BSDF"]["datablock"]
            out_node = mat_config["nodes"]["Material Output"]["datablock"]
            m_links.new(princ_node.outputs[0],amix_node.inputs[2])
            m_links.new(amix_node.outputs[0],out_node.inputs[0])
        elif self.passes.ALPHA!=None:
            a_node = mat_config["nodes"]["ALPHA"]["datablock"]
            princ_node = mat_config["nodes"]["Principled BSDF"]["datablock"]
            out_node = mat_config["nodes"]["Material Output"]["datablock"]
            amix_node = mat_config["nodes"]["ALPHA MIX"]["datablock"]
            m_links.new(princ_node.outputs[0],amix_node.inputs[2])
            m_links.new(amix_node.outputs[0],out_node.inputs[0])
            m_links.new(a_node.outputs[0],amix_node.inputs[0])

        if self.passes.TRANSMISSION==None:
            m_nodes.remove(mat_config["nodes"]["TRANSMISSION"]["datablock"])

        if hasattr(context.scene.cycles,"feature_set") and \
                context.scene.cycles.feature_set == 'EXPERIMENTAL':
            try:
                self.material.cycles.displacement_method = 'TRUE'
            except:
                print("Poliigon: Failed to set displacement method to TRUE, continuing")

        if self.passes.AO==None:
            m_nodes.remove(mat_config["nodes"]["AO"]["datablock"])
            m_nodes.remove(mat_config["nodes"]["AO + COLOR (Multiply)"]["datablock"])
            # re-create the appropriate link
            col = mat_config["nodes"]["COLOR"]["datablock"]
            princ_node = mat_config["nodes"]["Principled BSDF"]["datablock"]
            m_links.new(col.outputs[0], princ_node.inputs[0])

        if self.passes.DISPLACEMENT==None:
            m_nodes.remove(mat_config["nodes"]["DISPLACEMENT"]["datablock"])
            m_nodes.remove(mat_config["nodes"]["Bump"]["datablock"])
            norm = mat_config["nodes"]["Normal Map"]["datablock"]
            princ_node = mat_config["nodes"]["Principled BSDF"]["datablock"]
            m_links.new(norm.outputs[0], princ_node.inputs[17])

        # micro displacements currently not in use
        if self.microdisp==True and hasattr(self.material.cycles, "displacement_method"):
            self.material.cycles.displacement_method = 'TRUE'
            self.material.pmc_matprops.use_micro_displacements = True
            context.scene.cycles.feature_set = 'EXPERIMENTAL'

            # mute normal nodes, due to not being able to use both at once
            nrm = mat_config["nodes"]["NORMAL"]["datablock"]
            nrmmap = mat_config["nodes"]["Normal Map"]["datablock"]
            nrm.mute=True
            nrmmap.mute=True

        # # Make the solid view material color inherit from COL image
        # # via taking sampled-pixel average of rgb channels
        # # NOTE! Even with sampling, does add (significant) processing time/memory
        # # Possibility to do processing in background thread and assign back to
        # # the loaded materials (or in pre-loading state)
        # img = mat_config["nodes"]["COLOR"]["datablock"].image
        # if img:
        #     # import time
        #     # t0=time.time()

        #     pxlen = len(img.pixels)
        #     channels = pxlen/img.size[0]/img.size[1] # e.g. 3 or 4
        #     sampling = pxlen/channels/1024 # number of skips, at most 1024 samples
        #     if sampling<1: sampling=1 # less than 1024 pxls, so full sample/no skips
        #     skp = int(channels*sampling)

        #     # critical path, very slow (can't do slices on pixels directly)
        #     # also duplicates in memory
        #     lst = list(img.pixels)

        #     self.material.diffuse_color[0] = sum(lst[0::skp])/len(lst[0::skp]) # r
        #     self.material.diffuse_color[1] = sum(lst[1::skp])/len(lst[1::skp]) # g
        #     self.material.diffuse_color[2] = sum(lst[2::skp])/len(lst[2::skp]) # b
        #     lst = None # feabile attempt to tell python to release memory back sooner
        #     #print(">> COLOR PROCESS TIME IS: ",time.time()-t0)

    def build_cycles_principled(self):
        self.engine="cycles_principled"

        # base level material
        mat_config = {
            "nodes":{
                "Mapping": {
                    "type_id":"ShaderNodeMapping",
                    "type":"MAPPING",
                    "hide": False,
                    "location":mathutils.Vector((-860,0)),
                },
                "Texture Coordinate": {
                    "type_id":"ShaderNodeTexCoord",
                    "type":"TEX_COORD",
                    "hide": True,
                    "location":mathutils.Vector((-1040,190)),
                },
                "Material Output": {
                    "type_id":"ShaderNodeOutputMaterial",
                    "type":"OUTPUT_MATERIAL",
                    "location":mathutils.Vector((730,300)),
                },
                "Principled BSDF": {
                    "type_id":"ShaderNodeBsdfPrincipled",
                    "type":"BSDF_PRINCIPLED",
                    "distribution":"MULTI_GGX",
                    "location":mathutils.Vector((200,280)),
                },
                "AO": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"COLOR",
                    "hide": True,
                    "location":mathutils.Vector((-430,320)),
                },
                "REFLECTION": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"NONE",
                    "hide": True,
                    "location":mathutils.Vector((-430,120)),
                },
                "METALNESS": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"NONE",
                    "hide": True,
                    "location":mathutils.Vector((-430,130)),
                },
                "ROUGHNESS": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"NONE",
                    "hide": True,
                    "location":mathutils.Vector((-430,-40)),
                },
                "GLOSS": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"NONE",
                    "hide": True,
                    "location":mathutils.Vector((-430,20)),
                },
                "NORMAL": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"NONE",
                    "hide": True,
                    "location":mathutils.Vector((-430,-180)),
                },
                "DISPLACEMENT": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"NONE",
                    "hide": True,
                    "location":mathutils.Vector((-430,-100)),
                },
                "COLOR": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "hide": True,
                    "location":mathutils.Vector((-430,220)),
                },
                "SSS": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "hide": True,
                    "location":mathutils.Vector((-430,170)),
                },
                "AO + COLOR (Multiply)": {
                    "type_id":"ShaderNodeMixRGB",
                    "type":"MIX_RGB",
                    "hide": True,
                    "blend_type":"MULTIPLY",
                    "location":mathutils.Vector((-250,260)),
                },
                "Invert": {
                    "type_id":"ShaderNodeInvert",
                    "type":"INVERT",
                    "hide": True,
                    "location":mathutils.Vector((-250,40)),
                },
                "Normal Map": {
                    "type_id":"ShaderNodeNormalMap",
                    "type":"NORMAL_MAP",
                    "space":"TANGENT",
                    "location":mathutils.Vector((-250,-130)),
                },
                "Bump": {
                    "type_id":"ShaderNodeBump",
                    "type":"BUMP",
                    "location":mathutils.Vector((-50,0)),
                },
                "ALPHA MIX": {
                    "type_id":"ShaderNodeMixShader",
                    "type":"MIX_SHADER",
                    "location":mathutils.Vector((450,350)),
                },
                "Transparent BSDF": {
                    "type_id":"ShaderNodeBsdfTransparent",
                    "type":"TRANSPARENT",
                    "location":mathutils.Vector((200,400)),
                },
                "ALPHA": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"NONE",
                    "hide": True,
                    "location":mathutils.Vector((-430,400)),
                },
                "TRANSMISSION": {
                    "type_id":"ShaderNodeTexImage",
                    "type":"TEX_IMAGE",
                    "color_space":"NONE",
                    "hide": True,
                    "location":mathutils.Vector((-430,-60)),
                },
            },
            "links":[
                # (from_node, from_socket, to_node, to_socket)
                ("AO", 0, "AO + COLOR (Multiply)", 2),
                ("COLOR", 0, "AO + COLOR (Multiply)", 1),
                ("AO + COLOR (Multiply)", 0, "Principled BSDF", 0),
                ("REFLECTION", 0, "Principled BSDF", 5),
                ("GLOSS", 0, "Invert", 1),
                ("Invert", 0, "Principled BSDF", 7),
                ("NORMAL", 0, "Normal Map", 1),
                ("Normal Map", 0, "Bump",3),
                ("METALNESS", 0, "Principled BSDF", 4),
                ("Principled BSDF", 0, "Material Output", 0),
                ("DISPLACEMENT", 0, "Bump", 2),
                ("Bump", 0, "Principled BSDF", 17),
                ("SSS", 0, "Principled BSDF",3),
                ("TRANSMISSION", 0, "Principled BSDF",15),
                ("Texture Coordinate", 2, "Mapping", 0),
                ("Mapping", 0, "AO", 0),
                ("Mapping", 0, "COLOR", 0),
                ("Mapping", 0, "SSS", 0),
                ("Mapping", 0, "METALNESS", 0),
                ("Mapping", 0, "REFLECTION", 0),
                ("Mapping", 0, "GLOSS", 0),
                ("Mapping", 0, "ROUGHNESS", 0),
                ("Mapping", 0, "NORMAL", 0),
                ("Mapping", 0, "DISPLACEMENT", 0),
                ("Mapping", 0, "ALPHA", 0),
                ("Mapping", 0, "TRANSMISSION", 0),
                ("Transparent BSDF", 0, "ALPHA MIX", 1),
            ],
            "defaults":[
                # (node, input_index, value) for setting default socket value
                ("Normal Map",0, 1.0),
                ("AO + COLOR (Multiply)",1,(1,1,1,1)),
                ("Principled BSDF",3,(0,0,0,1)),
                ("AO + COLOR (Multiply)",0, 1),
                ("Principled BSDF",1,0.0)
            ]
        }
        return mat_config
    # define the allowed passname types
    class pass_names():
        def __init__(self):
            self.COLOR = None
            self.DISPLACEMENT = None
            self.GLOSS = None
            self.NORMAL = None
            self.REFLECTION = None
            self.METALNESS = None
            self.ROUGHNESS = None
            self.AO = None
            self.DIRT = None # not yet used
            self.SSS = None
            self.THUMBNAIL = None # not yet used
            self.ALPHAMASKED = None # full color with alpha channel
            self.ALPHA = None # black and white
            self.TRANSMISSION = None

        def __repr__(self):
            return "<pmc_workflow material passes filenames>"

        # define properties to expand names to match,
        # so that you can detect any of COLOR, COL, etc and it maps correctly
        # while still using the class structure

        @property
        def COL(self):
            return self.COLOR
        @COL.setter
        def COL(self, value):
            self.COLOR = value

        @property
        def DISP(self):
            return self.DISPLACEMENT
        @DISP.setter
        def DISP(self, value):
            self.DISPLACEMENT = value

        @property
        def MASK(self):
            return self.ALPHA
        @MASK.setter
        def MASK(self, value):
            self.ALPHA = value

        @property
        def NRM(self):
            return self.NORMAL
        @NRM.setter
        def NRM(self, value):
            self.NORMAL = value

        @property
        def NORMALS(self):
            return self.NORMAL
        @NORMALS.setter
        def NORMALS(self, value):
            self.NORMAL = value

        @property
        def REFL(self):
            return self.REFLECTION
        @REFL.setter
        def REFL(self, value):
            self.REFLECTION = value

        @property
        def METAL(self):
            return self.METALNESS
        @METAL.setter
        def METAL(self, value):
            self.METALNESS = value

    def save_settings_to_props(self):
        if self.material ==None:
            return
        self.material.pmc_matprops.workflow = self.workflow
        # self.material.pmc_matprops.engine = self.engine # not needed
        self.material.pmc_matprops.setname = self.setname
        self.material.pmc_matprops.status = json.dumps(self.status)
        self.material.pmc_matprops.size = "" if self.size==None else self.size
        self.material.pmc_matprops.use_ao = self.use_ao
        self.material.pmc_matprops.use_disp = self.use_disp
        self.material.pmc_matprops.use_sixteenbit = self.use_sixteenbit
        self.material.pmc_matprops.setpath = self.setpath

    def build_name(self):
        return str(self.setname)

    def get_passes(self):
        """
        Narrow list of prop types of valid pass names for image names
        Only inludes properties defined in __init__
        """
        return list(self.passes.__dict__) # vars(self.passes) also works

    def get_passes_loose_names(self):
        """
        Wide list of prop types of valid pass names for image names
        Includes e.g. both COLOR and COL
        """
        return [prop for prop in dir(self.passes) if "__" not in prop]
