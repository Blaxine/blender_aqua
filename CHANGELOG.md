# Changelog

## 0.22.0

**New**

- Still Water presets for real liquids: Water, Syrup, Oil, Chocolate, Thick Cream,
  Cream, Oatmeal and Honey. Each sets its own viscosity and material; the viscosity
  is calculated from the liquid's real figures and the size of your mesh. Water is
  now the default.
- Floating Objects use the density of the liquid they float in: ice sinks in oil,
  rubber floats in honey.

**Fixed**

- Installing over a version that had been turned off in the same Blender session
  failed with an error such as "has no attribute 'FLOAT_MATERIALS'".
- Runny liquids no longer gain volume: an 8 m³ cube of Water grew to 27 m³.
- Deleting a setup in a copied scene no longer removes the original scene's objects.
- A hose with Simulate Liquid now has its Bake button in the Simple view.
- Reactive Rain: Bake Again now re-bakes, and there is a button to free the bake.
- Deleting Water Lighting keeps a world you chose after adding it.
- Deleting the wave tank that extended the timeline puts the timeline back.
- Rain, Snow, Reactive Rain and the hose follow timeline changes at the same rate.
- A Floating Object can no longer also be turned into water or a rain pool.
- The Water Blast button says "Blast", and Create buttons always start from the
  default preset. "Also delete bake files" no longer stays ticked between deletes.
- Copy Report no longer rewrites ordinary words that match the file's name.
- Deleting the last hose no longer leaves an empty Water Obstacles collection.
- Corrected outdated wording.

**Known limits**

- Older presets such as Calm Pour can still gain volume in a splashing bake.
- Thick liquids spread to the edge of the simulation domain, so they can look like a block.
- A copied scene's setup shares its bake folder with the original.
