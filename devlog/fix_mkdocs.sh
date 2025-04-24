#!/bin/bash
# Back up the original file
cp /home/admin/dev/luxnix/mkdocs.yaml /home/admin/dev/luxnix/mkdocs.yaml.bak

# Fix the emoji constructor - replace the line with a standard emoji approach
sed -i 's/materialx\.emoji\.twemoji/material.extensions.emoji/g' /home/admin/dev/luxnix/mkdocs.yaml

# Alternatively, you may need to add the proper plugin in the plugins section:
# - material/plugins:
#     - material.extensions.emoji:
#         emoji_index: !!python/name:materialx.emoji.twemoji
#         emoji_generator: !!python/name:materialx.emoji.to_svg
