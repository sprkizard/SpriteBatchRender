"""
Sprite Batch Renderer, a Blender addon
Copyright (C) 2015-2019 Pekka Väänänen

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

See COPYING for details.
"""

"""
Renders the scene from multiple directions and saves the results in separate files.
The "front" direction is the same as Blender's front view, in other words your model
should face to the negative y direction.

Multiple frames can be rendered. The animation Frame Range is read from the regular
Start Frame and End Frame rendering properties.

Usage:
    Set your camera (called "Camera") to track an object placed at the origo.
    Place your camera to the distance and height you'd like it to render the object from.

    See Sprite Batch Rendering section of the Render-tab for controls.

    Note: the rendering process can't be canceled once started, so make sure your
    Frame Range and image resolution are correct.

"""

import bpy
import math
import sys
import time
import signal

from bpy.props import *

import mathutils
from math import radians

bl_info = \
    {
        "name" : "Sprite Batch Render (for SRB2 2.2.x)",
        "author" : "Pekka Väänänen <pekka.vaananen@iki.fi>",
        "version" : (1, 3, 3),
        "blender" : (2, 80, 0),
        "location" : "Render",
        "description" :
            "Renders the scene from multiple directions.",
        "warning" : "Open System Console to cancel rendering",
        "wiki_url" : "",
        "tracker_url" : "",
        "category" : "Render",
    }


#TODO: A0 can not be output
#TODO: errors when rendering with 5 steps and 8 directional is on and vice vers
def propertylimiter_update(self, context):
    if self.useFullRotation == True:
        self.myproperty += " man!"
    
    print("My property is:", self.myproperty)



class SpriteRenderSettings(bpy.types.PropertyGroup):
    path: StringProperty (
        name = "Sprite render path",
        description = """Where to save the sprite frames.\
 %s = frame name\
 %d = rotation number""",
        default = "",
        subtype = 'FILE_PATH'
    )

    steps: IntProperty (
        name = "Steps",
        description = "The number of different angles to render",
        default = 5
    )

    framenames: StringProperty (
        name = "Frame names",
        description = """The naming scheme for all frames.
 Each letter corresponds to a single frame.""",
        default = "ABCDEFGHIJKLMNOPQRSTUVWXYZ[+]^_`abcdefghijklmnopqrstuvwxyz{!}~"
    )

    anglenames: StringProperty (
        name = "Step names",
        description = """The naming scheme for rotation steps.
 Each letter corresponds to a single camera angle.""",
        default = "12345678"
    )

    anglenamessixteen: StringProperty (
        name = "Step names (16)",
        description = """The naming scheme for rotation steps.
 Each letter corresponds to a single camera angle.""",
        default = "192A3B4C5D6E7F8G"
    )

    target: StringProperty (
        name = "Target object",
        description = """The object to be rotated. Usually an Empty
 with the actual models as children.""",
        default = ""
    )

    useFullRotation : BoolProperty(
        name="Full Rotation",
        description="""The object will rotate in all
 directions. (8 or 16 Angles)""",
        default = False
    )

    actiondata : BoolProperty(
        name="Action data",
        description="""Blender will export individual Actions
 of the selected object.""",
        default = False
    )


class SpriteRenderOperator(bpy.types.Operator):
    bl_idname = "render.spriterender_operator"
    bl_label = "Sprite Render Operator"
    bl_options = {'REGISTER'}

    abort = False

    def execute(self, context):
        frame_start = context.scene.frame_start
        frame_end = context.scene.frame_end

        SpriteRenderOperator.abort = False

        def handler(signum, frame):
            print("Aborted rendering")
            SpriteRenderOperator.abort = True

        signal.signal(signal.SIGINT, handler)

        # Try hacking in steps here
        # TODO: lock Rotation steps selection to 5, 8, and 16 only
        useFullRotation = context.scene.sprite_render.useFullRotation
        steps = context.scene.sprite_render.steps
        finalsteps = context.scene.sprite_render.steps
        finalanglenames = context.scene.sprite_render.anglenames

        # Turned on full rotation
        if (useFullRotation  and steps == 8):
            finalsteps = 8; # steps is set to 8
        elif (useFullRotation and steps == 16):
            finalsteps = 16; # steps is set to 16 (assign new naming)
            finalanglenames = context.scene.sprite_render.anglenamessixteen
        else:
            # Hardcode 5, its not like srb2 will need another default
            finalsteps = 5;
            finalanglenames = context.scene.sprite_render.anglenames
        #-----------

        self.render(
            context.scene,
            context.scene.sprite_render.target,
            context.scene.sprite_render.path,
            finalsteps,
            context.scene.sprite_render.framenames,
            finalanglenames,
            frame_start,
            frame_end
        )

        signal.signal(signal.SIGINT, signal.default_int_handler)

        return {'FINISHED'}


    def render(self, scene, obj_name, filepath, steps, framenames, anglenames,\
            startframe=0, endframe=0):
        camera = scene.camera
        oldframe = scene.frame_current

        if not obj_name in scene.objects:
            self.report({'ERROR_INVALID_INPUT'}, "Target object '%s' not found!" % (obj_name))
            return
        obj = scene.objects[obj_name]

        if steps > len(anglenames) or steps <= 0:
            self.report({'ERROR_INVALID_INPUT'}, "Not enough step names specified for current rotation step count")
            return

        stepnames = anglenames

        if endframe-startframe > len(framenames)-1:
            self.report({'WARNING'}, "Only {0}/{1} frame names given".format(len(framenames), endframe-startframe))
            endframe = len(framenames)-1

        frame = startframe
        count = 0
        obj.rotation_mode = 'XYZ'
        orig_rotation = obj.rotation_euler.z
        done = False

        useFullRotation = scene.sprite_render.useFullRotation
        actiondata = scene.sprite_render.actiondata

        for f in range(startframe, endframe+1):
            scene.frame_current = f
            relative_frame = f - startframe

            print()

            # Just set to 0 for below swap-outs
            angle = 0

            for i in range(0, steps):

                # We only need angles of 45 for this (unless we are doing full 16 (new))
                if (steps == 16):
                    angle = 22.5 * i
                else:
                    angle = 45 * i

                # Rotate the model by the specified rotation angle type
                obj.rotation_euler.z = orig_rotation - radians(angle)
                print (obj.rotation_euler.z)

                bpy.context.view_layer.update()
                bpy.ops.wm.redraw_timer(type='DRAW_WIN_SWAP', iterations=1)

                stepname = stepnames[i]
                name = framenames[relative_frame]

                # Sprite Set Rotations
                rotationset = ["{0}{1}", "{0}{1}{2}{3}", "{0}{1}{2}{3}", "{0}{1}{2}{3}", "{0}{1}"]

                # Highlight our selections' action names if they are selected
                action_name = bpy.context.object.animation_data.action.name if actiondata == True else 'noaction'
                #print(str(action_name))

                # Export render for full 8, or mirrored rotation
                if (useFullRotation):
                    sprite_full_rotation_name = str(rotationset[0]).format(name, stepname)
                    print ("# Full Rotation Sprite name: " + (sprite_full_rotation_name) )

                    scene.render.filepath = output_object_sprite(filepath, obj_name, sprite_full_rotation_name, actiondata, action_name)
                else:
                    sprite_half_rotation_name = str(rotationset[i]).format(name, stepname, name, 9-i)
                    print ("# Half Rotation Sprite name: " + (sprite_half_rotation_name) )

                    scene.render.filepath = output_object_sprite(filepath, obj_name, sprite_half_rotation_name, actiondata, action_name)

                bpy.ops.render.render(animation=False, write_still=True)

                #print ("%d:%s: %f,%f" % (f, stepname, camera.location.x, camera.location.y))
                count += 1

                if SpriteRenderOperator.abort:
                    break

            if SpriteRenderOperator.abort:
                break


        print ("Rendered %d shots" % (count))
        scene.frame_current = oldframe

        obj.rotation_euler.z = orig_rotation


class SpriteRenderPanel(bpy.types.Panel):
    bl_idname = 'sprite_panel'
    bl_label = 'Sprite Batch Rendering'
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"

    def draw(self, context):
        l = self.layout
        framerow = l.row()
        props = context.scene.sprite_render

        l.column().prop_search(props, "target", context.scene, "objects",\
                icon='OBJECT_DATA', text="Target object")

        if props.target not in context.scene.objects:
            l.column().label(text = "Invalid target object '%s'!" % (props.target),
            icon='ERROR')

        l.row().prop(props, "steps", text="Rotation steps")
        #l.column().prop(props, "framenames", text="Frame names")

        frames = context.scene.frame_end - context.scene.frame_start
        if frames > len(props.framenames)-1:
            l.column().label(text = "Only {1} / {0} frame names given.".format(frames, len(props.framenames)-1), icon='ERROR')

        #l.column().prop(props, "anglenames", text="Step names")

        # Comment this out for now, since max steps are hard coded into the script
        # if len(props.anglenames) < props.steps:
        #     l.column().label(text = "Need at least %d step names." % (props.steps),
        #     icon='ERROR')

        l.row().prop(props, "path", text="Path format")

        l.row().prop(props, "useFullRotation", text="8 Directional")

        l.row().prop(props, "useDoubleFullRotation", text="16 Directional")

        l.row().prop(props, "actiondata", text="Use Action data")
        row = l.row()

        row.operator("render.spriterender_operator", text="Render Batch", icon='RENDER_ANIMATION')


classes = (SpriteRenderOperator, SpriteRenderPanel, SpriteRenderSettings)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    bpy.types.Scene.sprite_render = bpy.props.PointerProperty(type=SpriteRenderSettings)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.sprite_render


# TODO: find a better way to join a final path together
def output_object_sprite(path, objectname, rotationname, useaction=False, action=""):
    if (useaction == True):
        return path + str(objectname) + "/" + str(action) + "/" + str(objectname) + (rotationname) + ".png"
    else:
        return path + str(objectname) + "/" + str(objectname) + (rotationname) + ".png"


if __name__ == "__main__":
    register()
