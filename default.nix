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
      version = "0.25";
      src = fetchurl {
        url =
          "https://finalrewind.org/projects/Travel-Status-DE-DBRIS/Travel-Status-DE-DBRIS-0.25.tar.gz";
        hash = "sha256-KScMrdfsoUSxfsS534+4QHJxruVj16BJ7+GZxjsOmIw=";
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
        UUID
      ];
      meta = {
        description = "Interface to the online arrival/departure";
        license = with lib.licenses; [ artistic1 gpl1Plus ];
      };
    };
  motis-m = with perlPackages;
    buildPerlModule {
      pname = "Travel-Status-MOTIS";
      version = "0.0.2";
      src = fetchurl {
        url =
          "https://finalrewind.org/projects/Travel-Status-MOTIS/Travel-Status-MOTIS-0.02.tar.gz";
        hash = "sha256-bHt1M7yAxCQO8YetU+z888mW5YJ6+FeUB1J5QOAx2NI=";
      };
      doCheck = false;
      buildInputs = [ FileSlurp TestCompile TestPod ];
      propagatedBuildInputs = [
        ClassAccessor
        DateTime
        DateTimeFormatISO8601
        DateTimeFormatStrptime
        GISDistance
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
  TravelStatusDEVRR = with perlPackages;
    buildPerlModule {
      pname = "Travel-Status-DE-VRR";
      version = "3.19";
      src = fetchurl {
        url =
          "mirror://cpan/authors/id/D/DE/DERF/Travel-Status-DE-VRR-3.19.tar.gz";
        hash = "sha256-er8e4XfMpDoqDgC+SACZxfIye9jLr7S0CjbZVKZv+Ok=";
      };
      buildInputs = [ FileSlurp ];
      propagatedBuildInputs = [
        ClassAccessor
        DateTime
        DateTimeFormatStrptime
        JSON
        LWP
        LWPProtocolhttps
        URI
      ];
      meta = {
        description = "Unofficial VRR departure monitor";
        license = with lib.licenses; [ artistic1 gpl1Plus ];
      };
    };

  UUID = with perlPackages;
    buildPerlPackage {
      pname = "UUID";
      version = "0.37";
      src = fetchurl {
        url = "mirror://cpan/authors/id/J/JR/JRM/UUID-0.37.tar.gz";
        hash = "sha256-AvWv4rQ4bgm2yzo5taECt054mj4pcimUogqOMoXFYcc=";
      };
      buildInputs = [ DevelCheckLib TryTiny ];
      meta = {
        description = "Universally Unique Identifier library for Perl";
        license = lib.licenses.artistic2;
      };
    };
  DevelCheckLib = with perlPackages;
    buildPerlPackage {
      pname = "Devel-CheckLib";
      version = "1.16";
      src = fetchurl {
        url = "mirror://cpan/authors/id/M/MA/MATTN/Devel-CheckLib-1.16.tar.gz";
        hash = "sha256-hp04wljmRtzvZ2YJ8N18qQ8IX1bPb9cAGwGaXVuDH8o=";
      };
      buildInputs = [ CaptureTiny MockConfig ];
      meta = {
        description = "Check that a library is available";
        license = with lib.licenses; [ artistic1 gpl1Plus ];
      };
    };
  CaptureTiny = with perlPackages;
    buildPerlPackage {
      pname = "Capture-Tiny";
      version = "0.50";
      src = fetchurl {
        url = "mirror://cpan/authors/id/D/DA/DAGOLDEN/Capture-Tiny-0.50.tar.gz";
        hash = "sha256-ym6NfOdHHCvlThAJ9kw2fX7iM6KJTKz1Lr5vU7BOgeU=";
      };
      meta = {
        homepage = "https://github.com/dagolden/Capture-Tiny";
        description =
          "Capture STDOUT and STDERR from Perl, XS or external programs";
        license = lib.licenses.asl20;
      };
    };
  MockConfig = with perlPackages;
    buildPerlPackage {
      pname = "Mock-Config";
      version = "0.05";
      src = fetchurl {
        url = "mirror://cpan/authors/id/R/RU/RURBAN/Mock-Config-0.05.tar.gz";
        hash = "sha256-IAFwlsZGT71ZrnVJ+8Zjv7DJAU16w6RXqBp+QIJo9iw=";
      };
      meta = {
        description = "Temporarily set Config or XSConfig values";
        license = lib.licenses.artistic2;
      };
    };

  TryTiny = with perlPackages;
    buildPerlPackage {
      pname = "Try-Tiny";
      version = "0.32";
      src = fetchurl {
        url = "mirror://cpan/authors/id/E/ET/ETHER/Try-Tiny-0.32.tar.gz";
        hash = "sha256-7y1sqwutGOOrHE5hJcxfaVx+RZiZ9RJFHI+j74P6f8A=";
      };
      meta = {
        homepage = "https://github.com/p5sagit/Try-Tiny";
        description = "Minimal try/catch with proper preservation of $@";
        license = lib.licenses.mit;
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
      makeFullPerlPath [ JSON hafas-m dbris-m motis-m TravelStatusDEVRR ];
  in ''
    mkdir -p $out/bin
    cp $src/*.pl $out/bin
    wrapProgram $out/bin/json-hafas.pl --set PERL5LIB ${hafasperl}
    wrapProgram $out/bin/json-hafas-stationboard.pl --set PERL5LIB ${hafasperl}
    wrapProgram $out/bin/json-db-composition.pl --set PERL5LIB ${hafasperl}
    wrapProgram $out/bin/json-hafas-dbris-stopfinder.pl --set PERL5LIB ${hafasperl}
  '';

  propagatedBuildInputs = (with python310Packages; [
    discordpy
    setuptools
    haversine
    tomli
    tomli-w
    beautifulsoup4
  ]) ++ [ perl perlPackages.JSON hafas-m dbris-m motis-m TravelStatusDEVRR ];
  format = "pyproject";
}
