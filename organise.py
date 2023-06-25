import os
import shutil
import hashlib
import subprocess
from datetime import datetime
from PIL import Image
from PIL.ExifTags import TAGS

duplicateNameDifferentHashCount = 0
duplicateFileCount = 0
files_processed = 0
images_processed = 0
others_processed = 0

def get_exif(filename):
    image = Image.open(filename)
    image.verify()
    return image._getexif()

def get_month_taken(filename):
    month = None

    #1st attempt, get the exif header & parse DateTimeOriginal
    try:
        exif = get_exif(filename)
        for key, value in exif.items():
            name = TAGS.get(key, key)
            if name == 'DateTimeOriginal':            
                month = value.split(':')[1]
                return month
    except:
        pass

    #No exif header with date found, try getting created date using ffmpeg
    cmd = ['C:\\Portable\\ffmpeg\\bin\\ffmpeg.exe', '-i', filename, '-hide_banner']    
    output = ""
    try:
        output = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode('utf-8')
    except subprocess.CalledProcessError as e:
        output = e.output.decode('utf-8')
        
    for line in output.split('\n'):
        if 'creation_time' in line:            
            creation_time = line.split('creation_time   : ')[1].split('T')[0]            
            month = creation_time.split("-")[1]
            return month

    #Could not get the creation month from exif or video header, use file creation date:
    date_created = datetime.fromtimestamp(os.path.getmtime(filename))
    month = date_created.strftime("%m")
    return month + "date-uncertain"

def move_file(file_path, target_folder):
    global duplicateNameDifferentHashCount
    global duplicateFileCount
    file_name = os.path.basename(file_path)
    target_file_path = os.path.join(target_folder, file_name)
    if not os.path.exists(target_file_path):
        shutil.copy(file_path, target_file_path)
    else:        
        with open(file_path, 'rb') as f:
            file_hash = hashlib.md5(f.read()).hexdigest()
        with open(target_file_path, 'rb') as f:
            target_file_hash = hashlib.md5(f.read()).hexdigest()
        if file_hash != target_file_hash:          
            fn, ext = os.path.splitext(file_name)
            newFn = fn + "u" + str(duplicateNameDifferentHashCount) + ext #add a u as suffix, to avoid clash & to identify it as unique
            duplicateNameDifferentHashCount+=1
            new_target_file_path = os.path.join(target_folder, newFn)
            shutil.copy(file_path, new_target_file_path)
            print("\nFile {} copied to {} (identical filename, different hash)".format(file_name, new_target_file_path))
        else:
            print("\nFile {} already exists in {} - same hash - discarding".format(file_name, target_folder))
            duplicateFileCount+=1
        

def organiseAll():
    global files_processed
    global images_processed
    global others_processed

    root_folder = "D:\\02-foto\\Album-2016"
    organised_folder = root_folder + "-organised"
    
    for subdir, dirs, files in os.walk(root_folder):
        for file in files:
            files_processed+=1
            file_path = os.path.join(subdir, file)
            month_folder = get_month_taken(file_path)
            if (file.lower().endswith(".jpg")):
                images_processed+=1                
                destination_folder = os.path.join(organised_folder, "photos", month_folder)
                if not os.path.exists(destination_folder):
                    os.makedirs(destination_folder)
                print("P", end="")
                move_file(file_path, destination_folder)
                      
            else: #Also copy over non-jpg files
                others_processed+=1                
                month_folder = get_month_taken(file_path)
                destination_folder = os.path.join(organised_folder, "movies", month_folder)
                if not os.path.exists(destination_folder):
                    os.makedirs(destination_folder)
                print("M", end="")
                move_file(file_path, destination_folder)
             

organiseAll()
print ("\n# files processed: {}".format(files_processed))
print ("\n#   -> images: {}".format(images_processed))
print ("\n#   -> other: {}".format(others_processed))
print ("# duplicate files: {}".format(duplicateFileCount))
print ("# renamed files (same hash & filename): {}".format(duplicateNameDifferentHashCount))
