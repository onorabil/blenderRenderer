#!/bin/sh

#zip structure /REGULAR/3K

zip_name=$1
dir_name=${zip_name%.zip}
dir_name_3K=$dir_name'_3K'

unzip $zip_name
mv $dir_name $dir_name_3K
mv $dir_name_3K/REGULAR/3K/* $dir_name_3K/
