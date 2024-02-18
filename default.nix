with (import (import ./pinned-nixpkgs.nix) { });
let
  pyhafas = python310.pkgs.buildPythonPackage rec {
    pname = "pyhafas";
    version = "0.4.0";
    format = "setuptools";

    src = python310.pkgs.fetchPypi {
      inherit pname version;
      hash = "sha256-y0iUiodad50hR2FqdYgCDc0YbRGXpAo7AETU8AqVoCI=";
    };
    propagatedBuildInputs = with python310.pkgs; [ requests pytz ];

    doCheck = false;
};
    hafas-m = perlPackages.buildPerlModule {
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
    };
in
python310Packages.buildPythonPackage {
  src = builtins.path {
    path = ./.;
    name = "travelhook";
  };

  pname = "travelhook";
  version = "0.11.1";
  nativeBuildInputs = [ makeWrapper ];

  postFixup = ''
  mkdir -p $out/bin
  cp $src/json-hafas.pl $out/bin
  wrapProgram $out/bin/json-hafas.pl \
    --set PERL5LIB ${with perlPackages; makeFullPerlPath [
      JSON hafas-m
    ]}

  '';

  propagatedBuildInputs =
    (with python310Packages; [ discordpy setuptools haversine tomli tomli-w ]) ++
    [ pyhafas ] ++ [ perl perlPackages.JSON hafas-m ];
  format = "pyproject";
}
