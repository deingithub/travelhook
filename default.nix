with (import (import ./pinned-nixpkgs.nix) { });
let
  hafas-m = with perlPackages;
    buildPerlModule {
      pname = "Travel-Status-DE-DeutscheBahn";
      version = "6.15";
      src = fetchurl {
        url =
          "mirror://cpan/authors/id/D/DE/DERF/Travel-Status-DE-DeutscheBahn-6.15.tar.gz";
        hash = "sha256-0gAnC5LHPaJWbsWUqJ8tP3SYnMFCjrWOzu6La0K1Dd8=";
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
    dbris-m = with perlPackages;
      buildPerlModule {
        pname = "Travel-Status-DE-DBRIS";
        version = "0.10";
        src = fetchurl {
          url =
            "https://finalrewind.org/projects/Travel-Status-DE-DBRIS/Travel-Status-DE-DBRIS-0.10.tar.gz";
          hash = "sha256-iZ5MtqaQhY/aBqgTurg3gLW/Z/ad+Ff4drIZm7rLRHg=";
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

in python310Packages.buildPythonPackage {
  src = builtins.path {
    path = ./.;
    name = "travelhook";
  };

  pname = "travelhook";
  version = "0.28.4";
  nativeBuildInputs = [ makeWrapper ];

  postFixup = let
    hafasperl = with perlPackages;
      makeFullPerlPath [ JSON hafas-m dbris-m ];
  in ''
    mkdir -p $out/bin
    cp $src/*.pl $out/bin
    wrapProgram $out/bin/json-hafas.pl --set PERL5LIB ${hafasperl}
    wrapProgram $out/bin/json-hafas-stationboard.pl --set PERL5LIB ${hafasperl}
    wrapProgram $out/bin/json-db-composition.pl --set PERL5LIB ${hafasperl}
    wrapProgram $out/bin/json-hafas-dbris-stopfinder.pl --set PERL5LIB ${hafasperl}
  '';

  propagatedBuildInputs =
    (with python310Packages; [ discordpy setuptools haversine tomli tomli-w ])
    ++ [ perl perlPackages.JSON hafas-m dbris-m ];
  format = "pyproject";
}
