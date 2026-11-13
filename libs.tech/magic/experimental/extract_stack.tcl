drc off
gds read via_stack.gds
load STACK
select top cell
extract do local
extract all
ext2spice cthresh 0
ext2spice -o via_stack.spice
quit -noprompt
