"""An isolated, repeatable demo: no real games or Steam files are touched."""
from pathlib import Path
import os
import cairo
from .library import Library


def prepare_demo(seed=False):
    root=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'steam-library-metadata-manager-demo'
    library=Library(root)
    (root/'steam/userdata/123/config').mkdir(parents=True,exist_ok=True)
    if seed and not library.games():
        for index,(name,color) in enumerate((('Nebula Drift',(0.23,0.25,0.65)),('Echoes of the Valley',(0.12,0.45,0.36)),('Crimson Circuit',(0.65,0.18,0.3)))):
            surface=cairo.ImageSurface(cairo.FORMAT_ARGB32,360,540); c=cairo.Context(surface)
            gradient=cairo.LinearGradient(0,0,360,540)
            gradient.add_color_stop_rgb(0,*color); gradient.add_color_stop_rgb(1,.025,.045,.09)
            c.set_source(gradient); c.paint()
            c.set_source_rgba(1,1,1,.13)
            for n in range(5):
                c.arc(180,235,30+n*34,0,6.284); c.set_line_width(3); c.stroke()
            c.set_source_rgba(1,1,1,.8); c.move_to(180,130); c.line_to(245,270); c.line_to(115,270); c.close_path(); c.stroke()
            c.select_font_face('Sans',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD); c.set_font_size(27)
            for n,word in enumerate(name.split()): c.move_to(28,395+n*34); c.show_text(word.upper())
            c.set_font_size(12); c.move_to(28,510); c.show_text('DEMO LIBRARY / FICTIONAL GAME')
            image=root/f'demo-cover-{index}.png'; surface.write_to_png(str(image))
            executable=root/f'demo-{index}.exe'; executable.write_text('Inert demonstration file. Never execute.\n')
            game=library.new_game(); game.update(title=name,executable=str(executable),description='A fictional entry for reviewing the interface. This demo never reads or changes your actual Steam library.',release_date='2026',developers='Demo Studio',genres='Adventure, Exploration')
            game['artwork']['portrait']=library.add_image(image.read_bytes()); library.save(game)
    return library
