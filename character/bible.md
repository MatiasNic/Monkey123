# Biblia del personaje: el mono urbano

Esta es la regla madre del proyecto. La versión que lee el código es [`bible.yaml`](bible.yaml); este archivo explica el criterio.

## Identidad
- Es **el mismo macaco en todas las imágenes**. Hay que conservar los rasgos faciales, las proporciones, el color y la textura del pelaje (marrón claro cálido, **nunca verdoso ni oliva**; cara rosada-beige sin pelo), el tamaño, las orejas, el hocico corto y los ojos ámbar.
- **Nunca** puede aparecer como chimpancé, gorila, otro simio grande, caricatura, render 3D ni peluche.
- Tiene postura y comportamiento humanos, pero tiene que verse claramente como un mono real.
- Es un macaco **adulto** (nunca cría ni bebé), con el tamaño y la postura de las referencias: se sienta y se para como una persona y usa ropa de adulto que le queda bien.
- Personalidad visual: tranquilo, canchero, despreocupado, urbano y un poco irónico. Nunca posa como en una campaña.

### Referencias
- `reference/`: las imágenes **canónicas** de identidad. Se mandan al generador y son la base del QC de consistencia.
- `style_refs/`: referencias de encuadre y estilo (ropa, luz, escenas). Muestran a un simio con rasgos de chimpancé, así que **nunca se usan como referencia de identidad**.

## Expresiones
Son variadas y surgen de la situación. Nunca son artificiales.

## Poses y encuadres
Se rotan sin repetir; el catálogo completo está en `axes.pose`. Se combinan planos abiertos (con el mono ocupando una parte chica del cuadro) con retratos más cercanos.

## Ropa
Cambia según la situación. Estética humana contemporánea y urbana, con buen gusto.

## Situaciones
Escenas banales o absurdamente humanas (ver `situations_seed`). El humor sale del contraste entre la normalidad total de la escena y el hecho de que el protagonista sea un mono.

## Tono del contenido (`content`)
Cada foto tiene que poder subirse tal cual a Instagram: vida urbana tranquila y reconocible (viajar, un café, caminar, hacer mandados, trabajar, un rato en casa). Nada que se pueda leer como drogas, alcohol o cigarrillo; nada de objetos blancos ambiguos cerca de la cara, ni de un mono escondido, sucio, triste o perdido. El QC rechaza estas fotos aunque estén bien hechas.

## Estética fotográfica
- **Buscar:** lo mismo que las fotos de referencia. Foto real, limpia y nítida de celular moderno o cámara mirrorless, luz natural de día, colores reales, lugares luminosos y prolijos (balcón con plantas, panadería, café, local), momento cotidiano.
- **Evitar:** grano fuerte, flash directo, blanco y negro, viñeta, colores lavados o amarillentos, look cinematográfico, HDR, estética publicitaria y espejos (duplican manos).

Cada pieza usa un **look de cámara** del catálogo `camera_looks`. Todos son limpios; el post-proceso es mínimo.

## Entrega
Cuando se piden N imágenes, se entregan **N archivos independientes**. Nunca collage, grilla, contact sheet ni imagen dividida.
