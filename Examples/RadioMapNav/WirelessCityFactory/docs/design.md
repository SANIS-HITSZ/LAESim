# Design notes

The pipeline has four combinations: city only, city plus radio, city plus UE,
and city plus radio plus UE. City is mandatory and has no Sionna or Unreal
dependency. A run fingerprint includes the complete configuration except the
output location, so changing geometry or stage settings produces a new run.

The scene JSON is the single geometry truth source. The radio adapter consumes
that scene directly. The UE bundle is a visualization/simulation import
artifact and never supplies channel truth back to the radio stage.

The city generator uses independent deterministic seeds derived from the root
seed for morphology, buildings, station selection, and tasks. Buildings are
placed in road-delimited blocks with disjoint XY footprints; validation checks
all bounds, identifiers, parent blocks, and station/task clearance.

