from osgeo import ogr, osr, gdal

# Zone number map, zone_no -> FI
# Change the FI values if needed. 
fi_map = {
    '1': 0.02,
    '2': 0.95,
    '3': 0.05,
    '11': 0.05,
    '18': 0.9,
    '20': 0.0,
    '22': 0.0,
    '26': 0.5,
    '28': 0.05,
    '29': 0.0,
    '31': 0.9, # taking as commercial
}

def area_impervious(land_use_feature):
    """
    Calculate the impervious area of a land use feature.
    """
    fi = land_use_feature.GetField('fi')
    geom = land_use_feature.GetGeometryRef()
    return geom.Area() * fi

def assign_fi(land_use_feature):
    """
    Assign the fraction impervious to a land use feature based on the zone number.
    """
    land_use_id = land_use_feature.GetField('zone_no')
    land_use_id = str(land_use_id)
    if land_use_id in fi_map:
        return fi_map[land_use_id]
    raise ValueError(f"Zone ID {land_use_id} not found in fi_map")

def main():
    # Open the original shapefiles, Landuse is modefied in place to update the 'fi' field.
    basins = ogr.Open('vectors/basin.shp')
    land_use = ogr.Open('vectors/land_use.shp', 1)

    if basins is None or land_use is None:
        print("Failed to open shapefiles.")
        return

    basin_layer = basins.GetLayer()
    land_use_layer = land_use.GetLayer()

    # check if the land use layer has the 'fi' field, if it doesn't add it.
    if land_use_layer.GetLayerDefn().GetFieldIndex('fi') == -1:
        new_field = ogr.FieldDefn("fi", ogr.OFTReal)
        land_use_layer.CreateField(new_field)

    # Assign the FI for each land use feature based on the zone number.
    for land_use_feature in land_use_layer:
        fi = assign_fi(land_use_feature)
        land_use_feature.SetField("fi", fi)
        land_use_layer.SetFeature(land_use_feature)

    # Create a new shapefile for the updated basins
    driver = ogr.GetDriverByName('ESRI Shapefile')
    new_basins = driver.CreateDataSource('vectors/updated_basin.shp')
    new_basin_layer = new_basins.CreateLayer('updated_basin', geom_type=ogr.wkbPolygon)

    # Copy the schema from the original basin layer
    layer_defn = basin_layer.GetLayerDefn()
    for i in range(layer_defn.GetFieldCount()):
        field_defn = layer_defn.GetFieldDefn(i)
        new_basin_layer.CreateField(field_defn)

    # Add the new 'LandUseID' field
    new_field = ogr.FieldDefn("use_id", ogr.OFTString)
    new_basin_layer.CreateField(new_field)

    # Add the new field impervious area
    new_field = ogr.FieldDefn("imp_area", ogr.OFTReal)
    new_basin_layer.CreateField(new_field)

    # Create a spatial index for the land use layer
    land_use_layer.SetSpatialFilter(None)

    # Iterate through each basin feature
    for basin_feature in basin_layer:
        basin_geom = basin_feature.GetGeometryRef()

        # For each land_use that intersects the basin add impervious area
        land_use_layer.SetSpatialFilter(basin_geom)
        imperv_area = 0.
        land_use_ids = set()
        for land_use_feature in land_use_layer:
            land_use_geom = land_use_feature.GetGeometryRef()
            intersection_geom = basin_geom.Intersection(land_use_geom)
            # If the intersection is not clean filter out the feature that are not fully contained.
            if intersection_geom.GetArea() > 500:
                imperv_area += area_impervious(land_use_feature)
                land_use_ids.add(str(land_use_feature.GetField('zone_no')))

        # Create a new feature for the new basin layer
        new_basin_feature = ogr.Feature(new_basin_layer.GetLayerDefn())
        new_basin_feature.SetGeometry(basin_geom)
        for i in range(layer_defn.GetFieldCount()):
            new_basin_feature.SetField(layer_defn.GetFieldDefn(i).GetNameRef(), basin_feature.GetField(i))
        new_basin_feature.SetField("use_id", ', '.join(land_use_ids))
        new_basin_feature.SetField("imp_area", imperv_area)
        new_basin_layer.CreateFeature(new_basin_feature)

    # Spatial join the centroids with the new basins.
    # Open the centrodids shapefile.
    centroids = ogr.Open('vectors/centroids.shp', 1)

    if centroids is None:
        print("Failed to open centroids shapefile.")
        return
    
    centroid_layer = centroids.GetLayer()
    
    # update the centroids with the basin fraction impervious area
    for centroid_feature in centroid_layer:
        # Spatial filter to find the basin that contains the centroid
        centroid_geom = centroid_feature.GetGeometryRef()
        new_basin_layer.SetSpatialFilter(centroid_geom)
        for basin_feature in new_basin_layer:
            basin_geom = basin_feature.GetGeometryRef()
            if basin_geom.Contains(centroid_geom):
                imp_area = basin_feature.GetField('imp_area')
                basin_area = basin_geom.Area()
                fi = imp_area / basin_area
                centroid_feature.SetField('fi', fi)
                centroid_layer.SetFeature(centroid_feature)
                break
    
    # Cleanup
    land_use_layer.SetSpatialFilter(None)
    new_basins = None
    basins = None
    land_use = None
    centroids = None

if __name__ == '__main__':
    main()