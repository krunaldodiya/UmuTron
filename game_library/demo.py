"""An isolated demo. Play is disabled; synthetic files never execute."""
from pathlib import Path
import os
import cairo
from .library import Library


def prepare_demo(seed=False):
    root=Path(os.environ.get('XDG_CACHE_HOME',Path.home()/'.cache'))/'game-library-launcher-demo'
    library=Library(root)
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
            game=library.new_game(); game.update(title=name,executable=str(executable),description='A fictional entry for reviewing the interface. This demo never runs games or changes your actual library.',release_date='2026',developers='Demo Studio',genres='Adventure, Exploration')
            game['artwork']['portrait']=library.add_image(image.read_bytes())
            import io
            hero=cairo.ImageSurface(cairo.FORMAT_ARGB32,1120,280);hc=cairo.Context(hero);hc.set_source(gradient);hc.paint()
            hc.set_source_rgba(1,1,1,.15)
            for n in range(6):hc.arc(840,140,25+n*25,0,6.284);hc.stroke()
            output=io.BytesIO();hero.write_to_png(output);game['artwork']['hero']=library.add_image(output.getvalue())
            logo=cairo.ImageSurface(cairo.FORMAT_ARGB32,360,70);lc=cairo.Context(logo);lc.select_font_face('Sans',cairo.FONT_SLANT_NORMAL,cairo.FONT_WEIGHT_BOLD);lc.set_font_size(23);lc.set_source_rgb(1,1,1);lc.move_to(6,40);lc.show_text(name.upper())
            output=io.BytesIO();logo.write_to_png(output);game['artwork']['logo']=library.add_image(output.getvalue());library.save(game)
    return library
