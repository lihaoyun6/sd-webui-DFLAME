import os
import platform
import modules
import gradio as gr

from PIL import Image
from modules import shared
from modules.shared import opts
from modules.ui_common import update_generation_info, save_files, folder_symbol
from modules import scripts, script_callbacks, call_queue, ui_common

fake_img_path = os.path.join(scripts.basedir(),"images","result.png")

def create_output_panel(tabname, outdir):
    from modules import shared
    import modules.generation_parameters_copypaste as parameters_copypaste

    def open_folder(f):
        if not os.path.exists(f):
            print(f'Folder "{f}" does not exist. After you create an image, the folder will be created.')
            return
        elif not os.path.isdir(f):
            print(f"""
WARNING
An open_folder request was made with an argument that is not a folder.
This could be an error or a malicious attempt to run code on your computer.
Requested path was: {f}
""", file=sys.stderr)
            return

        if not shared.cmd_opts.hide_ui_dir_config:
            path = os.path.normpath(f)
            if platform.system() == "Windows":
                os.startfile(path)
            elif platform.system() == "Darwin":
                sp.Popen(["open", path])
            elif "microsoft-standard-WSL2" in platform.uname().release:
                sp.Popen(["wsl-open", path])
            else:
                sp.Popen(["xdg-open", path])

    with gr.Column(variant='panel', elem_id=f"{tabname}_results"):
        with gr.Group(elem_id=f"{tabname}_gallery_container") as gallery_container:
            result_gallery = gr.Gallery(label='Output', show_label=False, elem_id=f"{tabname}_gallery").style(columns=4)
        if opts.data.get("DFLAME_show_fake_image", True):
            fake_result_gallery = gr.Gallery(label='Output', visible=False, value=[Image.open(fake_img_path)], show_label=False, elem_id=f"{tabname}_fake_gallery").style(columns=4)
        else:
            fake_result_gallery = gr.Gallery(label='Output', visible=False, show_label=False, elem_id=f"{tabname}_fake_gallery").style(columns=4)

        generation_info = None
        with gr.Column():
            with gr.Row(elem_id=f"image_buttons_{tabname}", elem_classes="image-buttons"):
                open_folder_button = gr.Button(folder_symbol, visible=not shared.cmd_opts.hide_ui_dir_config)

                if tabname != "extras":
                    save = gr.Button('Save', elem_id=f'save_{tabname}')
                    save_zip = gr.Button('Zip', elem_id=f'save_zip_{tabname}')

                buttons = parameters_copypaste.create_buttons(["img2img", "inpaint", "extras"])
                DFLAME_hide = gr.Button(opts.data.get("DFLAME_button_text", "Send to DFLAME"), elem_id=f'DFLAME_hide_{tabname}')
                DFLAME_show = gr.Button(opts.data.get("DFLAME_button_text", "Send to DFLAME"), elem_id=f'DFLAME_show_{tabname}', visible=False)

            open_folder_button.click(
                fn=lambda: open_folder(shared.opts.outdir_samples or outdir),
                inputs=[],
                outputs=[],
            )

            if tabname != "extras":
                download_files = gr.File(None, file_count="multiple", interactive=False, show_label=False, visible=False, elem_id=f'download_files_{tabname}')

                with gr.Group():
                    html_info = gr.HTML(elem_id=f'html_info_{tabname}', elem_classes="infotext")
                    html_log = gr.HTML(elem_id=f'html_log_{tabname}')

                    generation_info = gr.Textbox(visible=False, elem_id=f'generation_info_{tabname}')
                    if tabname == 'txt2img' or tabname == 'img2img':
                        generation_info_button = gr.Button(visible=False, elem_id=f"{tabname}_generation_info_button")
                        generation_info_button.click(
                            fn=update_generation_info,
                            _js="function(x, y, z){ return [x, y, selected_gallery_index()] }",
                            inputs=[generation_info, html_info, html_info],
                            outputs=[html_info, html_info],
                            show_progress=False,
                        )

                    save.click(
                        fn=call_queue.wrap_gradio_call(save_files),
                        _js="(x, y, z, w) => [x, y, false, selected_gallery_index()]",
                        inputs=[
                            generation_info,
                            result_gallery,
                            html_info,
                            html_info,
                        ],
                        outputs=[
                            download_files,
                            html_log,
                        ],
                        show_progress=False,
                    )

                    save_zip.click(
                        fn=call_queue.wrap_gradio_call(save_files),
                        _js="(x, y, z, w) => [x, y, true, selected_gallery_index()]",
                        inputs=[
                            generation_info,
                            result_gallery,
                            html_info,
                            html_info,
                        ],
                        outputs=[
                            download_files,
                            html_log,
                        ]
                    )

                    DFLAME_hide.click(
                        fn=lambda: ({"visible": False, "__type__": "update"}, {"visible": False, "__type__": "update"}, {"visible": False, "__type__": "update"}, {"visible": False, "__type__": "update"}, {"visible": True, "__type__": "update"}, {"visible": True, "__type__": "update"}),
                        inputs=[],
                        outputs=[gallery_container, DFLAME_hide, html_info, html_log, fake_result_gallery, DFLAME_show],
                    )

                    DFLAME_show.click(
                        fn=lambda: ({"visible": True, "__type__": "update"}, {"visible": True, "__type__": "update"}, {"visible": True, "__type__": "update"}, {"visible": True, "__type__": "update"}, {"visible": False, "__type__": "update"}, {"visible": False, "__type__": "update"}),
                        inputs=[],
                        outputs=[gallery_container, DFLAME_hide, html_info, html_log, fake_result_gallery, DFLAME_show],
                    )

            else:
                html_info_x = gr.HTML(elem_id=f'html_info_x_{tabname}')
                html_info = gr.HTML(elem_id=f'html_info_{tabname}', elem_classes="infotext")
                html_log = gr.HTML(elem_id=f'html_log_{tabname}')

            paste_field_names = []
            if tabname == "txt2img":
                paste_field_names = modules.scripts.scripts_txt2img.paste_field_names
            elif tabname == "img2img":
                paste_field_names = modules.scripts.scripts_img2img.paste_field_names

            for paste_tabname, paste_button in buttons.items():
                parameters_copypaste.register_paste_params_button(parameters_copypaste.ParamBinding(
                    paste_button=paste_button, tabname=paste_tabname, source_tabname="txt2img" if tabname == "txt2img" else None, source_image_component=result_gallery,
                    paste_field_names=paste_field_names
                ))

            return result_gallery, generation_info if tabname != "extras" else html_info_x, html_info, html_log

class DFLAME(scripts.Script):
    def title(self):
        return 'DFLAME (Don\'t F**king Look At Me)'

    def describe(self):
        return "Hide/show live preview and result gallery with one-click"

    def show(self, is_img2img):
        return scripts.AlwaysVisible

def hijack():
    ui_common.create_output_panel = create_output_panel

def create_settings_items():
    section = ('DFLAME', 'DFLAME')
    opts.add_option("DFLAME_show_fake_image", shared.OptionInfo(
        True, "Show fake result pictures in fake gallery (requires restart)", section=section
    ))
    opts.add_option("DFLAME_button_text", shared.OptionInfo(
        "Send to DFLAME", "Button label (requires restart)", section=section
    ))

script_callbacks.on_before_ui(hijack)
scripts.script_callbacks.on_ui_settings(create_settings_items)