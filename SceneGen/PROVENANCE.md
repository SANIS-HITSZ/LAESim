# Provenance

The original Wireless City Factory delivery supplied the procedural city generator, the
canonical scene schema, OBJ exporter, Sionna RT mesh-stage integration, and the
Unreal/AirSim import workflow. The canonical coordinate system is right-handed,
metres, and +Z-up. UE marker coordinates use the documented Y-flip and
metre-to-centimetre transform.

The radio stage uses Sionna RT with native Windows CUDA/OptiX, a transparent
disconnected multilayer measurement mesh, two equal-area triangles per XY cell,
and reduction to [Tx,Z,Y,X]. These choices are part of the active repository
implementation and are recorded in the generated manifests.

The UMa and UMi deployment labels are calibration references based on 3GPP
TR 38.901 v18.0.0, especially Table 7.2-1 and the calibration tables:
https://www.etsi.org/deliver/etsi_tr/138900_138999/138901/18.00.00_60/tr_138901v180000p.pdf
They are not claims that one parameter set describes every commercial network.
The 4.9 GHz carrier, 100 MHz bandwidth, finite-window site count, receiver
heights, and production ray budget remain explicit project experiment choices.

AirSim plugin files and satellite assets are external third-party components.
SceneGen/scripts/SetupLAESim.ps1 copies this LAESim checkout's components into the selected UE
project and does not modify the source checkout. Their licenses remain those
provided by the respective upstream projects and asset authors.

The repository source and documentation use the MIT License in LICENSE. Generated
maps, local build products, and external vendor files are excluded from ordinary
source tracking by .gitignore.

The maintained implementation is integrated into LAESim: generic scene tools
live in SceneGen, radio tools in RadioSim, and navigation in Examples/RadioMapNav.
The original delivery ZIP and inventory remain under Examples/RadioMapNav/reference.
SceneGen and RadioSim retain this delivery's source license and provenance;
this integration does not change third-party licensing.
