// Discovery of all military-tag values, not an inventory completeness claim.
// OSM country-area membership is source scope, not an approved border decision.
[out:json][timeout:50][maxsize:268435456];
area["ISO3166-1"="RU"]["admin_level"="2"]->.r;
(
  nwr["military"](area.r);
  wr["landuse"="military"](area.r);
);
out tags center;
