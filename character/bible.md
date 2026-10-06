# Biblia del personaje: el mono urbano

Esta es la regla madre del proyecto. La versión que lee el código es [`bible.yaml`](bible.yaml); este archivo explica el criterio.

## Identidad
- Es **el mismo macaco en todas las imágenes**. Hay que conservar los rasgos faciales, las proporciones, el color y la textura del pelaje (marrón claro cálido, **nunca verdoso ni oliva**; cara rosada-beige sin pelo), el tamaño, las orejas, el hocico corto y los ojos ámbar.
- **Nunca** puede aparecer como chimpancé, gorila, otro simio grande, caricatura, render 3D ni peluche.
- Tiene postura y comportamiento humanos, pero tiene que verse claramente como un mono real.
- La escala es chica y creíble dentro del ambiente.
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
- **Buscar:** textura de negativo, grano real, contraste moderado, colores levemente imperfectos, luces prácticas, leve imperfección óptica, profundidad de campo creíble, sensación de foto espontánea. Ocasionalmente, motion blur, aberración cromática sutil o flash frontal discreto.
- **Evitar:** look cinematográfico, HDR, estética publicitaria, imagen perfecta o con cara de "generado por IA".

Cada pieza usa un **look de cámara** del catálogo `camera_looks`. Cada look tiene su fragmento de prompt y sus parámetros de post-proceso.

## Entrega
Cuando se piden N imágenes, se entregan **N archivos independientes**. Nunca collage, grilla, contact sheet ni imagen dividida.
