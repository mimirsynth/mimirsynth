**English** · [Español](Grafo)

# Graph

A **map** view of the knowledge: entities are nodes and facts are the edges joining them. Ideal for discovering how everything relates, seeing **where each piece of knowledge came from** and spotting oddities (isolated entities, duplicate nodes, unexpected relations).

## Loading controls
- **Seeds:** how many starting entities are loaded (the most connected), from 5 to 100.
- **Hops:** how many neighbourhood "hops" (0–2) are brought in around each seed.
- **Min. degree:** hides nodes with fewer connections than that number (refines the view when there is a lot of noise).
- **Find node:** selects the first entity whose name contains the text and zooms to it.
- **Invalidated:** includes the facts that stopped being true (drawn with a **dashed line**).
- **Travel in time:** a slider from the first episode to today (the last 90 days if the brain has no episodes, for example one with imported facts only); the map shows what was known **on that day**.

The bottom indicator counts the loaded nodes and facts, and warns if the load was **trimmed by the node limit**. While the graph is being computed, a «Computing the graph…» notice covers the canvas.

When you arrive from [[Knowledge]] (an entity mentioned in a document), the graph is centred on that entity and it is selected.

## Layouts and 2D / 3D
- **Force** (the default), **Radial** (rings by level) and **Tree** (parents centred over their children). Changing layout moves every node to its new place with an animation.
- **2D** or **3D**. 3D is drawn with WebGL and only loaded when you choose it; it keeps the same controls, legend, halos, focus, tooltip and expansion. If the browser has no WebGL, a notice says so and the graph stays in 2D. If 3D is still slow even with reduced effects, a notice offers **Back to 2D**.
- Positions are stable: reloading does not reshuffle the graph.

## Halos by origin
In the **Force** layout, every **origin** wraps its nodes in a translucent halo of its colour, with its name and count. A node backed by several origins sits where their halos overlap, and origins that share more nodes are placed next to each other. Nodes without a known origin go to a neutral area below. In 3D a halo is a translucent volume with its name above it.

**Group by** chooses what counts as an origin, without loading the graph again:
- **Origin type** (the default): Text, Message, JSON, or Document, File folder or Wiki when the knowledge came from a document.
- **Document:** the document it was promoted from.
- **Contributor:** the person who sent the proposal.
- **Agent / token:** the API token that sent it.
- **Entity type:** groups by type instead of by provenance.

A node's origins are those of the episodes that mention it and of its visible facts. The **8 largest** origins get their own halo; the rest are grouped as «Others».

- The **Origins** legend lists them: click one to **turn its halo on or off**. **Halos by origin** turns them all off (it is only available in the Force layout).
- What is backed by **2 or more origins** is drawn with a ring on the node and thicker edges. **Only confirmed by 2 or more origins** keeps just those nodes and the relations between them. It is not available when grouping by **Entity type**, since there are no origins to count.

Loading provenance adds some time in very large brains.

## Interaction
- **Hover a node:** after a short pause its neighbourhood is highlighted and the rest dims; a tooltip shows its name, type, connections and origins, and particles run along its current facts.
- **Click a node:** keeps its neighbourhood highlighted (also with reduced effects) and opens the side panel with its summary, its type and **degree**, its **Origins**, its **facts** (invalidated ones struck through) and the **documents that mention it** (linking to [[Knowledge]]). **View page** opens its [[Entity page]].
- **Click an edge:** shows the fact, between which entities, since when it is valid, when it stopped being true (if it did) and its **Origins**.
- **Right-click a node:** **expands its neighbourhood**; the new nodes grow out of it. **Undo last expansion** removes the last one.
- **Wheel** to zoom, **drag the background** to move; **Fit to view** frames everything.
- **Drag a node:** it **stays where you drop it**, marked with a dot. **Double-click** releases it; **Reset positions** releases them all and lays the graph out again.
- **Pause / Resume simulation** (Force only): stops the force layout where it is.
- Above 60 visible nodes a **minimap** shows the whole graph and the current view; click it to centre the view there.

## Legend
Besides **Origins**, the legend lists **Types** (the node colours) and **Relations**, each with its count. Click an item to **hide or show** it without moving the rest of the graph. The legend can be collapsed.

## Graphic effects
The **Graphic effects** choice is stored **in this browser, per device** (not in your account), because what matters is the device's graphics card. The [[Cypher query]] screen follows the same choice.
- **Automatic** (the default): full effects, dropping to reduced by itself if the device stays slow (under about 30 frames per second); the selector then reads «Automatic (reduced)».
- **Full:** entry animations, particles, minimap and up to 120 labels.
- **Reduced:** keeps the halos but drops the entry animation, the particles and the minimap, shows fewer labels (60), and hovering no longer dims the rest; in 3D it also draws simpler spheres.

If your system asks for **reduced motion**, nothing moves on its own whatever the setting: no entry animation or particles, the layout settles at once and zooming jumps. In any mode, nothing is animated while the graph is at rest.

## Exporting
- **Export JSON:** the loaded nodes and facts.
- **Export image:** a PNG of what you see.

## Tips
- Start with few seeds and expand what interests you.
- Very large nodes connected to everything are usually generic entities ("server"): candidates to review in [[Vocabulary]].
- Two nearly identical nodes (same name with a different version or capitalisation) are **possible duplicates**: merge them under *Vocabulary → Duplicates*.
- Group by **Contributor** or **Agent / token** to see who taught what, and turn on **Only confirmed by 2 or more origins** to keep what independent sources agree on.
