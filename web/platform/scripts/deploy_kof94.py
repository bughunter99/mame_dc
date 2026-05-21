import shutil, re

src_js = r'D:\data3\mame_dc\kof94.js'
dst_js = r'D:\data3\mame_dc\web\platform\frontend\static\wasm\mame.js'
src_wasm = r'D:\data3\mame_dc\kof94.wasm'
dst_wasm = r'D:\data3\mame_dc\web\platform\frontend\static\wasm\kof94.wasm'

# Read kof94.js
t = open(src_js, encoding='utf-8', errors='replace').read()

# Apply stackAlloc fallback patch
old = 'stackAlloc=function(){return(stackAlloc=Module["asm"]["stackAlloc"]).apply(null,arguments)}'
new = 'stackAlloc=function(){return(stackAlloc=Module["asm"]["stackAlloc"]||Module["asm"]["__emscripten_stack_alloc"]).apply(null,arguments)}'
patched = t.replace(old, new)

if patched == t:
    print('WARNING: stackAlloc patch not applied - pattern not found')
else:
    print('stackAlloc patch applied')

open(dst_js, 'w', encoding='utf-8', newline='').write(patched)
print(f'mame.js written: {len(patched)} chars')

# Copy wasm
shutil.copy2(src_wasm, dst_wasm)
import os
print(f'kof94.wasm copied: {os.path.getsize(dst_wasm):,} bytes')
