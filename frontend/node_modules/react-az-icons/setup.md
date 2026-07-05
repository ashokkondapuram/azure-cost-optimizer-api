# Setup Guide

After cloning the repository execute:

```
npm install
```

Install TypeScript

```
npm install -g typescript
```

And we are ready to go!

## Create a new component

1. Place the SVG files in the `[root]/svgs` directory. 
2. Rename files to PascalCase without numbers, spaces or any other special chracters. For many files check [batch renaming](#batch-renaming) below.
3. Execute `npm run build`, further details in [Build process](#build-process)
4. Verify the Icon in any of your projects and
5. Open a PR!

## Build process

### 1. Initially the build process will execute:
```
node scripts --typescript svgs src
```
Which generates react components in TypeScript in the folder `src`, and finally: 

### 2. Transpiling into JavaScript
TypeScript files are transpiled by executing the command `tsc`, which is configured by the files [tsconfig.json](./tsconfig.json).

# Batch Renaming
Batch rename files by replacing values as shown in the command below.

```bash
# verify the command initially 
for file in *; do echo mv $file ${file//OLD_VALUE/NEW_VALUE}; done

# remove `echo` and execute it to apply changes
for file in *; do mv $file ${file//OLD_VALUE/NEW_VALUE}; done
```

# How to fix a SVG using [Inkscape](https://inkscape.org/)

1. Open the SVG in inkscape.
2. Make the changes.
3. **(Important)** Crop to selection, hotkey CTRL + SHIFT + R and Save.

# Removing whitespace 
Using the open source Inkscape you can automate removal of canvas which doesn't contain the icon. (Or you can manually do that as described above.)

```
foreach ($file in $files){
    inkscape --verb=FitCanvasToDrawing --verb=FileSave --verb=FileQuit ".\$file"
}
```