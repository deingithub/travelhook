with (import (import ./pinned-nixpkgs.nix) { });
perlPackages.buildPerlModule {
    pname = "Travel-Status-DE-DeutscheBahn";
    version = "5.04";
    src = fetchurl {
      url = "mirror://cpan/authors/id/D/DE/DERF/Travel-Status-DE-DeutscheBahn-5.04.tar.gz";
      hash = "sha256-1NW3d/X8VS86bjx2+9ML+xaLeCAmXPdSg6nBD9cV/E0=";
    };
    doCheck = false;
    buildInputs = with perlPackages; [ FileSlurp TestCompile TestPod ];
    propagatedBuildInputs = with perlPackages; [ ClassAccessor DateTime DateTimeFormatStrptime JSON LWP LWPProtocolhttps ListMoreUtils ];
    meta = {
      description = "Interface to the online arrival/departure";
      license = with lib.licenses; [ artistic1 gpl1Plus ];
    };
  }
