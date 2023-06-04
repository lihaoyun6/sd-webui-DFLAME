import os
import io
import time
import base64
import platform
import modules
import gradio as gr
import modules.shared as shared

from modules.shared import opts
from modules.progress import ProgressRequest, ProgressResponse
from modules.ui_common import update_generation_info, save_files, folder_symbol
from modules import scripts, script_callbacks, shared, call_queue, ui_common, progress

def show():
    opts.hide_live_preview = False
    return ({"visible": True, "__type__": "update"}, {"visible": True, "__type__": "update"}, {"visible": True, "__type__": "update"}, {"visible": True, "__type__": "update"}, {"visible": False, "__type__": "update"}, {"visible": False, "__type__": "update"})

def hide():
    opts.hide_live_preview = True
    return ({"visible": False, "__type__": "update"}, {"visible": False, "__type__": "update"}, {"visible": False, "__type__": "update"}, {"visible": False, "__type__": "update"}, {"visible": True, "__type__": "update"}, {"visible": True, "__type__": "update"})

def progressapi(req: ProgressRequest):
    active = req.id_task == modules.progress.current_task
    queued = req.id_task in modules.progress.pending_tasks
    completed = req.id_task in modules.progress.finished_tasks

    if not active:
        return ProgressResponse(active=active, queued=queued, completed=completed, id_live_preview=-1, textinfo="In queue..." if queued else "Waiting...")

    progress = 0

    job_count, job_no = shared.state.job_count, shared.state.job_no
    sampling_steps, sampling_step = shared.state.sampling_steps, shared.state.sampling_step

    if job_count > 0:
        progress += job_no / job_count
    if sampling_steps > 0 and job_count > 0:
        progress += 1 / job_count * sampling_step / sampling_steps

    progress = min(progress, 1)

    elapsed_since_start = time.time() - shared.state.time_start
    predicted_duration = elapsed_since_start / progress if progress > 0 else None
    eta = predicted_duration - elapsed_since_start if predicted_duration is not None else None

    id_live_preview = req.id_live_preview
    shared.state.set_current_image()

    if opts.live_previews_enable and shared.state.id_live_preview != req.id_live_preview:
        image = shared.state.current_image
        if image is not None:
            buffered = io.BytesIO()

            if opts.live_previews_image_format == "png":
                # using optimize for large images takes an enormous amount of time
                if max(*image.size) <= 256:
                    save_kwargs = {"optimize": True}
                else:
                    save_kwargs = {"optimize": False, "compress_level": 1}

            else:
                save_kwargs = {}

            image.save(buffered, format=opts.live_previews_image_format, **save_kwargs)
            base64_image = base64.b64encode(buffered.getvalue()).decode('ascii')
            live_preview = f"data:image/{opts.live_previews_image_format};base64,{base64_image}"
            if opts.hide_live_preview:
                live_preview = f"data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAACXBIWXMAAAsTAAALEwEAmpwYAAAADElEQVQImWP4//8/AAX+Av5Y8msOAAAAAElFTkSuQmCC"
            id_live_preview = shared.state.id_live_preview
        else:
            live_preview = None
    else:
        live_preview = None

    return ProgressResponse(active=active, queued=queued, completed=completed, progress=progress, eta=eta, live_preview=live_preview, id_live_preview=id_live_preview, textinfo=shared.state.textinfo)

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
        fake_result_gallery = gr.Gallery(label='Output', visible=False, show_label=False, elem_id=f"{tabname}_fake_gallery").style(columns=4)

        generation_info = None
        with gr.Column():
            with gr.Row(elem_id=f"image_buttons_{tabname}", elem_classes="image-buttons"):
                open_folder_button = gr.Button(folder_symbol, visible=not shared.cmd_opts.hide_ui_dir_config)

                if tabname != "extras":
                    save = gr.Button('Save', elem_id=f'save_{tabname}')
                    save_zip = gr.Button('Zip', elem_id=f'save_zip_{tabname}')

                buttons = parameters_copypaste.create_buttons(["img2img", "inpaint", "extras"])
                DFLAME_hide = gr.Button('Send to other', elem_id=f'DFLAME_hide_{tabname}')
                DFLAME_show = gr.Button('Send to other', elem_id=f'DFLAME_show_{tabname}', visible=False)

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
                        fn=hide,
                        inputs=[],
                        outputs=[gallery_container, DFLAME_hide, html_info, html_log, fake_result_gallery, DFLAME_show],
                    )

                    DFLAME_show.click(
                        fn=show,
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
    opts.hide_live_preview = False
    ui_common.create_output_panel = create_output_panel
    progress.progressapi = progressapi

script_callbacks.on_before_ui(hijack)