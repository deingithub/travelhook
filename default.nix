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
  hafas-m = with perlPackages;
    buildPerlModule {
      pname = "Travel-Status-DE-DeutscheBahn";
      version = "6.08";
      src = fetchurl {
        url =
          "mirror://cpan/authors/id/D/DE/DERF/Travel-Status-DE-DeutscheBahn-6.08.tar.gz";
        hash = "sha256-12B+WazUmvH+eIhO25YERnePoLRnKVAMRCeSB6yq+jU=";
      };
      doCheck = false;
      buildInputs = [ FileSlurp TestCompile TestPod ];
      propagatedBuildInputs = [
        ClassAccessor
        DateTime
        DateTimeFormatStrptime
        JSON
        LWP
        LWPProtocolhttps
        ListMoreUtils
      ];
      meta = {
        description = "Interface to the online arrival/departure";
        license = with lib.licenses; [ artistic1 gpl1Plus ];
      };
    };
  GISDistance = with perlPackages;
    buildPerlModule {
      pname = "GIS-Distance";
      version = "0.20";
      src = fetchurl {
        url = "mirror://cpan/authors/id/B/BL/BLUEFEET/GIS-Distance-0.20.tar.gz";
        sha256 =
          "b2b2f8774cddab6e3e49d34988efafe8fe0d500ff6d57b61f86614095bf1423e";
      };
      buildInputs = [ ModuleBuildTiny Test2Suite ];
      propagatedBuildInputs =
        [ ClassMeasure ConstFast namespaceclean strictures ];
      meta = {
        homepage = "https://github.com/bluefeet/GIS-Distance";
        description = "Calculate geographic distances";
        license = with lib.licenses; [ artistic1 gpl1Plus ];
      };
    };
  ClassMeasure = with perlPackages;
    buildPerlModule {
      pname = "Class-Measure";
      version = "0.10";
      src = fetchurl {
        url =
          "mirror://cpan/authors/id/B/BL/BLUEFEET/Class-Measure-0.10.tar.gz";
        sha256 =
          "c0b79eb09a66cc41fb83aadbd24874372b465a74407b96e0722994eefbfd24ca";
      };
      buildInputs = [ ModuleBuildTiny Test2Suite ];
      propagatedBuildInputs = [ SubExporter ];
      meta = {
        homepage = "https://github.com/bluefeet/Class-Measure";
        description = "Create, compare, and convert units of measurement";
        license = with lib.licenses; [ artistic1 gpl1Plus ];
      };
    };
  TravelStatusDEIRIS = with perlPackages;
    buildPerlModule {
      pname = "Travel-Status-DE-IRIS";
      version = "1.98";
      src = fetchurl {
        url =
          "mirror://cpan/authors/id/D/DE/DERF/Travel-Status-DE-IRIS-1.98.tar.gz";
        hash = "sha256-eIK8N0Duj7G10rzHGSkJK0tbAzN2j5mTDiqJsFMPc9A=";
      };
      buildInputs = [
        FileSlurp
        JSON
        TestCompile
        TestFatal
        TestNumberDelta
        TestPod
        TextCSV
      ];
      propagatedBuildInputs = [
        ClassAccessor
        DateTime
        DateTimeFormatStrptime
        GISDistance
        LWP
        LWPProtocolhttps
        ListCompare
        ListMoreUtils
        ListUtilsBy
        TextLevenshteinXS
        XMLLibXML
      ];
      meta = {
        description = "Interface to IRIS based web departure monitors";
        license = with lib.licenses; [ artistic1 gpl1Plus ];
      };
    };
  TravelStatusDEDBWagenreihung = with perlPackages;
    buildPerlModule {
      pname = "Travel-Status-DE-DBWagenreihung";
      version = "0.18";
      src = fetchurl {
        url =
          "mirror://cpan/authors/id/D/DE/DERF/Travel-Status-DE-DBWagenreihung-0.18.tar.gz";
        hash = "sha256-EHqIqsjbPUBcN3uFm/aimHyDQnHNty64ld26EZwGhmM=";
      };
      buildInputs = [ TestCompile TestPod ];
      propagatedBuildInputs = [ ClassAccessor JSON LWP TravelStatusDEIRIS ];
      meta = {
        description = "Interface to Deutsche Bahn Wagon Order API";
        license = with lib.licenses; [ artistic1 gpl1Plus ];
      };
    };

in python310Packages.buildPythonPackage {
  src = builtins.path {
    path = ./.;
    name = "travelhook";
  };

  pname = "travelhook";
  version = "0.13.3";
  nativeBuildInputs = [ makeWrapper ];

  postFixup = let
    hafasperl = with perlPackages;
      makeFullPerlPath [ JSON hafas-m TravelStatusDEDBWagenreihung ];
  in ''
    mkdir -p $out/bin
    cp $src/*.pl $out/bin
    wrapProgram $out/bin/json-hafas.pl --set PERL5LIB ${hafasperl}
    wrapProgram $out/bin/json-hafas-stationboard.pl --set PERL5LIB ${hafasperl}
    wrapProgram $out/bin/json-db-composition.pl --set PERL5LIB ${hafasperl}
  '';

  propagatedBuildInputs =
    (with python310Packages; [ discordpy setuptools haversine tomli tomli-w ])
    ++ [ pyhafas ]
    ++ [ perl perlPackages.JSON hafas-m TravelStatusDEDBWagenreihung ];
  format = "pyproject";
}
