# AUTOGENERATED! DO NOT EDIT! File to edit: ../nbs/encoder.ipynb.

# %% auto 0
__all__ = ['ENCODER_EMBS_MODULE_NAME', 'DCAE_torch', 'kwargs_to_gpu_', 'kwargs_to_cpu_', 'get_acts',
           'get_enc_embs_ensure_batch_size_', 'get_enc_embs_MVP', 'get_enc_embs_MVP_set_stride_set_batch_size',
           'get_enc_embs_moment', 'get_enc_embs_moment_reconstruction', 'watch_gpu', 'get_enc_embs_moirai',
           'get_enc_embs', 'get_enc_embs_set_stride_set_batch_size']

# %% ../nbs/encoder.ipynb 2
from .memory import *
from .utils import Time
from .utils import print_flush

# %% ../nbs/encoder.ipynb 5
import pandas as pd
import numpy as np
from fastcore.all import *
from tsai.callback.MVP import *
from tsai.imports import *
from tsai.models.InceptionTimePlus import InceptionTimePlus
from tsai.models.explainability import get_acts_and_grads
from tsai.models.layers import *
from tsai.data.validation import combine_split_data
from fastai.callback.hook import hook_outputs
from momentfm import MOMENTPipeline
from gluonts.dataset.pandas import PandasDataset
import time
import einops

# %% ../nbs/encoder.ipynb 8
class DCAE_torch(Module):
    def __init__(self, c_in, seq_len, delta, nfs=[64, 32, 12], kss=[10, 5, 5],
                 pool_szs=[2,2,3], output_fsz=10):
        """
        Create a Deep Convolutional Autoencoder for multivariate time series of `d` dimensions,
        sliced with a window size of `w`. The parameter `delta` sets the number of latent features that will be
        contained in the Dense layer of the network. The the number of features
        maps (filters), the filter size and the pool size can also be adjusted."
        """
        assert all_equal([len(x) for x in [nfs, kss, pool_szs]], np.repeat(len(nfs), 3)), \
            'nfs, kss, and pool_szs must have the same length'
        assert np.prod(pool_szs) == nfs[-1], \
            'The number of filters in the last conv layer must be equal to the product of pool sizes'
        assert seq_len % np.prod(pool_szs) == 0, \
            'The product of pool sizes must be a divisor of the window size'
        layers = []
        for i in range_of(kss):
            layers += [Conv1d(ni=nfs[i-1] if i>0 else c_in, nf=nfs[i], ks=kss[i]),
                       nn.MaxPool1d(kernel_size=pool_szs[i])]
        self.downsample = nn.Sequential(*layers)
        self.bottleneck = nn.Sequential(OrderedDict([
            ('flatten', nn.Flatten()),
            ('latent_in', nn.Linear(seq_len, delta)),
            ('latent_out', nn.Linear(delta, seq_len)),
            ('reshape', Reshape(nfs[-1], seq_len // np.prod(pool_szs)))
        ]))
        layers = []
        for i in reversed(range_of(kss)):
            layers += [Conv1d(ni=nfs[i+1] if i != (len(nfs)-1) else nfs[-1],
                              nf=nfs[i], ks=kss[i]),
                       nn.Upsample(scale_factor=pool_szs[i])]
        layers += [Conv1d(ni=nfs[0], nf=c_in, kernel_size=output_fsz)]
        self.upsample = nn.Sequential(*layers)


    def forward(self, x):
        x = self.downsample(x)
        x = self.bottleneck(x)
        x = self.upsample(x)
        return x

# %% ../nbs/encoder.ipynb 11
ENCODER_EMBS_MODULE_NAME = {
    InceptionTimePlus: 'backbone', # for mvp based models
    DCAE_torch: 'bottleneck.latent_in'#,
    #MoiraiForecast: 'mask_encoding' #TODO: check
    
}

# %% ../nbs/encoder.ipynb 13
def kwargs_to_gpu_(**kwargs):
    for key in kwargs:
        try: #if not able to be moved, just not move it
            kwargs[key] = kwargs[key].to("cuda")
        except:
            continue
    
def kwargs_to_cpu_(**kwargs):
    for key in kwargs:
        try: #if not able to be moved, just not move it
            kwargs[key] = kwargs[key].cpu()
        except:
            continue
   

# %% ../nbs/encoder.ipynb 14
def get_acts(
    model : torch.nn.Module, 
    module: torch.nn.Module, 
    cpu   : bool, 
    verbose : int = 0,
    **model_kwargs #Parameters of the model
):
    if verbose > 0:
        print(f"--> get acts ")
    if cpu:
        print(f"get acts | Moving to cpu")
        for key in model_kwargs:
            try: #if not able to be moved, just not move it
                model_kwargs[key] = model_kwargs[key].cpu()
            except:
                continue
        model.to("cpu")
    else:
        print(f"get acts | Moving to gpu")
        for key in model_kwargs:
            try: #if not able to be moved, just not move it
                model_kwargs[key] = model_kwargs[key].to("cuda")
            except:
                continue
        model.to("cuda")
    if verbose > 0:
        print(f"get acts | Add hooks")
    h_act = hook_outputs([module], detach = True, cpu = cpu, grad = False)
    if verbose > 0:
        print(f"get acts | Run forward")
    preds = model.eval()(**model_kwargs)
    if verbose > 0:
        print(f"get acts -->")
    return [o.stored for o in h_act]

# %% ../nbs/encoder.ipynb 16
from fastai.learner import Learner
from tsai.data.core import TSDataLoaders

# %% ../nbs/encoder.ipynb 17
def get_enc_embs_ensure_batch_size_(
    dls        : TSDataLoaders,
    batch_size : int = None,
    verbose    : int = 0
) -> None:
    if batch_size is None:
        if verbose > 1: 
            print("[ Get Encoder Embeddings Ensure Batch Size ] No batch size proposed")
        if dls.bs == 0: 
            if verbose > 1: 
                print("[ Get Encoder Embeddings Ensure Batch Size ] Using value 64 as 0 is not a valid value.")
            enc_learn.dls.bs = 64
        elif verbose > 1: 
            print(f"[ Get Encoder Embeddings Ensure Batch Size ] Using the original value: {dls.bs}")
    else:
        dls.bs = batch_size
        if verbose > 1: 
            print(f"[ Get Encoder Embeddings Ensure Batch Size ] Batch size proposed. Using {dls.bs}")

# %% ../nbs/encoder.ipynb 18
def get_enc_embs_MVP(
    X               : List [ List [ List [ float ] ] ], 
    enc_learn       : Learner, 
    module          : str  = None, 
    cpu             : bool = False, 
    average_seq_dim : bool = True, 
    to_numpy        : bool = True,
    batch_size      : int  = None,
    verbose         : int  = 0
):
    """
        Get the embeddings of X from an encoder, passed in `enc_learn as a fastai
        learner. By default, the embeddings are obtained from the last layer
        before the model head, although any layer can be passed to `model`.
        Input
        - `cpu`: Whether to do the model inference in cpu of gpu (GPU recommended)
        - `average_seq_dim`: Whether to aggregate the embeddings in the sequence dimensions
        - `to_numpy`: Whether to return the result as a numpy array (if false returns a tensor)
        - `batch_size`: force data loader to use the input batch size
        - `verbose`: print flag. More big, more information.
    """
    
    if cpu:
        if verbose > 0: print("[ Get Encoder Embeddings ] CPU")
        enc_learn.dls.cpu()
        enc_learn.cpu()
    else:
        if verbose > 0: print("[ Get Encoder Embeddings ] --> GPU")
        if verbose > 1: print("[ Get Encoder Embeddings ] GPU | Ensure empty cache")
        torch.cuda.empty_cache()
        if verbose > 1: print("[ Get Encoder Embeddings ] GPU | Move & exec into CUDA")
        enc_learn.dls.cuda()
        enc_learn.cuda()
        if torch.cuda.is_available():
            if verbose > 1: 
                print("[ Get Encoder Embeddings ] GPU | CUDA is available")
                print(f"[ Get Encoder Embeddings ] GPU | CUDA is available | current device id {torch.cuda.current_device()}")
                print(f"[ Get Encoder Embeddings ] GPU | CUDA is available | current device name {torch.cuda.get_device_name(torch.cuda.current_device())}")            
        else:
            if verbose > 1: print("[ Get Encoder Embeddings ] GPU | CUDA is not available")
        if verbose > 0: print("[ Get Encoder Embeddings ] GPU -->")

    #if verbose > 0: print("[ Get Encoder Embeddings ] Ensure the correct batch size")
    #get_enc_embs_ensure_batch_size_(enc_learn.dls, batch_size, verbose)
    
    if verbose > 0: print("[ Get Encoder Embeddings ] Set dataloader from X (enc_learn does not contain dls)")
    aux_dl = enc_learn.dls.valid.new_dl(X=X)
    get_enc_embs_ensure_batch_size_(aux_dl, batch_size, verbose)
    if verbose > 0: print("[ Get Encoder Embeddings ] Get module")
    module = nested_attr(enc_learn.model,ENCODER_EMBS_MODULE_NAME[type(enc_learn.model)]) if module is None else module
    
    if verbose > 0: print("[ Get Encoder Embeddings ] get_acts_and_grads ")
    if verbose > 1: print(f"[ Get Encoder Embeddings ] get_acts_and_grads bs = {aux_dl.bs}")
    
    embs = [
        get_acts_and_grads(
            model   = enc_learn.model,
            modules = module,
            x       = xb[0], 
            cpu     = cpu
        )[0] 
        for xb in aux_dl
    ]
    if verbose > 0: print("[ Get Encoder Embeddings ] get_acts_and_grads | --> Concat")
    if not cpu:
        if verbose > 1: print("[ Get Encoder Embeddings ] get_acts_and_grads | Concat | Check neccesary & free memory")
        total_emb_size = sum([emb.element_size() * emb.nelement() for emb in embs])
        free_memory = torch.cuda.get_device_properties(0).total_memory - torch.cuda.memory_allocated()
        if (total_emb_size < free_memory):
            if verbose > 1: print("[ Get Encoder Embeddings ] get_acts_and_grads | Concat | Check neccesary & free memory | Fits in GPU -> Computing in GPU")
            embs=[emb.cuda() for emb in embs]
        else:
            if verbose > 1: print("[ Get Encoder Embeddings ] get_acts_and_grads | Concat | Check neccesary & free memory | Does not fit in GPU -> Computing in CPU")
            embs=[emb.cpu() for emb in embs]
    if verbose > 1: print("[ Get Encoder Embeddings ] get_acts_and_grads | Concat | to_concat")
    embs = to_concat(embs)
    if verbose > 0: print("[ Get Encoder Embeddings ] get_acts_and_grads | Concat -->")
    
    if verbose > 0: print("[ Get Encoder Embeddings ] Reduce to 2 dimensions.")
    if embs.ndim == 3 and average_seq_dim: embs = embs.mean(axis=2)
    if verbose > 0: print("[ Get Encoder Embeddings ] Ensure CPU saving & numpy format")
    if to_numpy: embs = embs.numpy() if cpu else embs.cpu().numpy()
    return embs

# %% ../nbs/encoder.ipynb 19
def get_enc_embs_MVP_set_stride_set_batch_size(
    X                  : List [ List [ List [ float ] ] ], 
    enc_learn          : Learner, 
    stride             : int, 
    batch_size         : int, 
    module             : str  = None, 
    cpu                : bool = False, 
    average_seq_dim    : bool = True, 
    to_numpy           : bool = True, 
    verbose            : int  = 0, 
    time_flag          : bool = False, 
    chunk_size         : int  = 0, 
    check_memory_usage : bool = False
):
    """
        Get the embeddings of X from an encoder, passed in `enc_learn as a fastai
        learner. By default, the embeddings are obtained from the last layer
        before the model head, although any layer can be passed to `model`.
        Input
        - `X`: encoder input
        - `enc_learn`: trained encoder
        - `stride`: stride used for the training. Neccesary for adjusting the encoder input
        - `batch_size`: value to force the dataloader to use.
        - `module`: for geting the embeddings of an specific layer.
        - `cpu`: Whether to do the model inference in cpu of gpu (GPU recommended)
        - `average_seq_dim`: Whether to aggregate the embeddings in the sequence dimensions
        - `to_numpy`: Whether to return the result as a numpy array (if false returns a tensor)
        - `verbose`: For printing messages. More big, more messages.
        - `time_flag`: To take note of the execution time required by this function
        - `chunk_size`: For spliting the embedings reading in batches of `chunk_size` size.
        - `check_memory_usage`: For showing messages of the current state of the memory.
    """
    if time_flag:
        t_start = time.time()
    if verbose > 0:
        print("--> get_enc_embs_set_stride_set_batch_size")
    if check_memory_usage: gpu_memory_status()
    X = X[::stride]
    enc_learn.dls.bs = batch_size 

    get_enc_embs_ensure_batch_size_(enc_learn.dls, batch_size, verbose)
    
    if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | Check CUDA | X ~ ", X.shape[0])
    if cpu:
        if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | Get enc embs CPU")
        enc_learn.dls.cpu()
        enc_learn.cpu()
    else:
        if torch.cuda.is_available():
            if verbose > 0: 
                print("get_enc_embs_set_stride_set_batch_size | CUDA device id:", torch.cuda.current_device())
                print("get_enc_embs_set_stride_set_batch_size | CUDA device name: ", torch.cuda.get_device_name(torch.cuda.current_device()))
                print("get_enc_embs_set_stride_set_batch_size | Ensure empty cache & move 2 GPU")
            torch.cuda.empty_cache()
            enc_learn.dls.cuda()
            enc_learn.cuda()
        else:
            if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | No cuda available. Set CPU = true")
            cpu = True
            
    get_enc_embs_ensure_batch_size_(enc_learn.dls, batch_size, verbose)

    if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | Set dataset from X (enc_learn does not contain dls)")
    aux_dl = enc_learn.dls.valid.new_dl(X=X)
    aux_dl.bs = enc_learn.dls.bs if enc_learn.dls.bs>0 else 64
    if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | Get module")
    module = nested_attr(enc_learn.model,ENCODER_EMBS_MODULE_NAME[type(enc_learn.model)]) if module is None else module
    
    if verbose > 0: 
        #print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | module ", module)
        print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | aux_dl len", len(aux_dl))
        print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | aux_dl.batch_len ", len(next(iter(aux_dl))))
        print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | aux_dl.bs ", aux_dl.bs)
        if (not cpu):
            total = torch.cuda.get_device_properties(device).total_memory
            used = torch.cuda.memory_allocated(torch.cuda.current_device())
            reserved = torch.cuda.memory_reserved(torch.cuda.current_device())
            print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | total_mem ", total)
            print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | used_mem ", used)
            print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | reserved_mem ", reserved)
            print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | available_mem ", total-reserved)
            sys.stdout.flush()
                                              
    if (cpu or ( chunk_size == 0 )):
        embs = [
            get_acts_and_grads(
                model=enc_learn.model,
                modules=module, 
                x=xb[0], 
                cpu=cpu
            )[0] 
            for xb in aux_dl
        ]
        if not cpu: embs=[emb.cpu() for emb in embs]
    else:
        embs = []
        total_chunks=max(1,round(len(X)/chunk_size))
        if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | aux_dl len | " + str(len(X)) + " chunk size: " + str(chunk_size) + " => " + str(total_chunks) + " chunks")
        for i in range(0, total_chunks):
            if verbose > 0: 
                print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | Chunk [ " + str(i) + "/"+str(total_chunks)+"] => " + str(round(i*100/total_chunks)) + "%")
                sys.stdout.flush()
            chunk = [batch for (n, batch) in enumerate(aux_dl) if (chunk_size*i <= n  and chunk_size*(i+1) > n) ]
            chunk_embs = [
                get_acts_and_grads(
                    model=enc_learn.model,
                    modules=module,
                    x=xb[0], 
                    cpu=cpu
                )[0]
                for xb in chunk
            ]
            # Mueve los embeddings del bloque a la CPU
            chunk_embs = [emb.cpu() for emb in chunk_embs]
            embs.extend(chunk_embs)
            torch.cuda.empty_cache()
        if verbose > 0: 
            print("get_enc_embs_set_stride_set_batch_size | Get acts and grads | 100%")
            sys.stdout.flush()
    
    if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | concat embeddings")
    
    embs = to_concat(embs)
    
    if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | Reduce")
    
    if embs.ndim == 3 and average_seq_dim: embs = embs.mean(axis=2)
    
    if verbose > 0: print("get_enc_embs_set_stride_set_batch_size | Convert to numpy")
    
    if to_numpy: 
        if cpu or chunk_size > 0:
            embs = embs.numpy() 
        else: 
            embs = embs.cpu().numpy()
            torch.cuda.empty_cache()
    if time_flag:
        t = time.time()-t_start
        if verbose > 0:
            print("get_enc_embs_set_stride_set_batch_size " + str(t) + " seconds -->")
        else:
            print("get_enc_embs_set_stride_set_batch_size " + str(t) + " seconds")
    if check_memory_usage: gpu_memory_status()
    if verbose > 0: 
        print("get_enc_embs_set_stride_set_batch_size -->")
    return embs

# %% ../nbs/encoder.ipynb 20
def get_enc_embs_moment(
    X               : List [ List [ List [ float ] ] ], 
    enc_learn       : Learner, 
    cpu             : bool = False, 
    to_numpy        : bool = True,
    verbose         : int  = 0,
    average_seq_dim : bool = True,
    padd_step       : int  = 2
):
    if verbose > 0: 
        print_flush("--> get_enc_embs_moment")
    # Move tensor and model to GPU
    if cpu or not torch.cuda.is_available():
        if verbose > 0: 
            print_flush("get_enc_embs_moment | Using CPU (maybe no cuda available)")
        cpu = True
        enc_learn.cpu()
        enc_learn.cpu()
    else:
        if verbose > 0: 
            print_flush("get_enc_embs_moment | Using CUDA")
        enc_learn.to("cuda")
    if verbose > 0: print_flush("get_enc_embs_moment | Convert y")
    enc_learn.eval()
    if cpu:
        y = torch.from_numpy(X).cpu().float()
    else:
        y = torch.from_numpy(X).to("cuda").float()
    # Get output
    with torch.no_grad():
        if verbose > 0: 
            print_flush("get_enc_embs_moment | Get outputs")
        outputs = enc_learn(y)
        if verbose > 0:
            print(f"get_enc_embs_moment | Final shape: X ~ {y.shape}")
                
    #| move tensors and models back to CPU
    if not cpu:
        y = y.detach().cpu().numpy()
    if verbose > 0: 
        print_flush("get_enc_embs_moment | Get Embeddings")
    embeddings = outputs.embeddings.detach().cpu()
    if average_seq_dim: 
        embeddings = embeddings.mean(dim = 1)
    if to_numpy:
        embeddings = embeddings.cpu().numpy()
    if verbose > 0: 
        print_flush("get_enc_embs_moment -->")
    return embeddings

# %% ../nbs/encoder.ipynb 21
def get_enc_embs_moment_reconstruction(
    X               : List [ List [ List [ float ] ] ], 
    enc_learn       : Learner, 
    cpu             : bool = False, 
    to_numpy        : bool = True,
    verbose         : int  = 0,
    average_seq_dim : bool = True,
    padd_step       : int  = 2
):
    """
    For reconstruction sometimes mask get invalid values
    To avoid them, the last dimension (sequence length) is padded with 0's until the error is skippedd
    It should only get one iteration as it seems to be some MOMENT internal configuration for patches.
    """
    if cpu:
        enc_learn.cpu()
    else:
        enc_learn.to("cuda")
        y = torch.from_numpy(X).to("cuda").float()
    success = False
    while not success:
        try:
            if verbose > 1: 
                print(f"get_enc_embs_moment_reconstruction | x_enc ~ {y.shape}")
            acts = get_acts(
                model = enc_learn,
                #module = enc_learn.encoder.dropout,
                module = enc_learn.head.dropout,
                cpu = cpu,
                verbose = verbose,
                x_enc = y
            )
            embs = acts[0]
            success = True
            if verbose > 1: 
                print(f"get_enc_embs_moment_reconstruction | embs ~ {embs.shape}")
        except Exception as e:
            if verbose > 0:
                print(f"get_enc_embs_moment | About to pad X (encoder input) | exception {e} | padd step: {padd_step}")
            y = torch.nn.functional.pad(y,(0,padd_step))
    if average_seq_dim: 
        embs = embs.mean(dim = 1).mean(dim = 1)
    if to_numpy:
        embs = embs.cpu().numpy()
    return embs

# %% ../nbs/encoder.ipynb 23
import uni2ts.model.moirai.module as moirai
import uni2ts.model.moirai.forecast as moirai_forecast

# %% ../nbs/encoder.ipynb 24
import torch.profiler as profiler

# %% ../nbs/encoder.ipynb 25
def watch_gpu(func, **kwargs):
    """
    Wrapper to execute GPU profiler
    Parameters: 
    - func: function to monitor
    - kwargs: func parameters
    Returns:
    - result of /func/.
    """
    with profiler.profile(
        activities=[profiler.ProfilerActivity.CPU, profiler.ProfilerActivity.CUDA],
        schedule=profiler.schedule(wait=1, warmup=1, active=3, repeat=2),  # Configuración de ciclos
        on_trace_ready=profiler.tensorboard_trace_handler('./log_dir'),  # Guarda los resultados en un archivo para visualización
        record_shapes=True,  # Registra la forma de los tensores
        profile_memory=True,  # Perfil de memoria
        with_stack=True  # Incluye la información de la pila
    ) as prof:
        # Ejecuta la función dentro del perfilador
        result = func(**kwargs)
    
    # Mostrar el uso de la GPU durante y después de la ejecución
    print(prof.key_averages().table(sort_by="cuda_memory_usage", row_limit=10))
    return result

# %% ../nbs/encoder.ipynb 26
def get_enc_embs_moirai(
    enc_input       : List [ List [ List [ Float ] ] ], 
    enc_model       : moirai.MoiraiModule, 
    cpu             : False,
    average_seq_dim : bool = True, 
    to_numpy        : bool = True,
    verbose         : int  = 0,
    patch_size      : int  = 8,
    time            : bool = False
):
    if time: 
        timer = Time()
        timer.start()
    if verbose > 0: 
        print("--> get_enc_embs_moirai")
    # Move tensor and model to GPU
    past_target = einops.rearrange(
        torch.as_tensor(enc_input, dtype = torch.float32),
        "n_windows n_vars window_size -> n_windows window_size n_vars"
    )
    if cpu or not torch.cuda.is_available():
        if verbose > 0: print("get_enc_embs_moirai | Using CPU (maybe no cuda available)")
        cpu = True
        enc_model.cpu()
        past_target.cpu()
    else:
        if verbose > 0: print("get_enc_embs_moirai | Using CUDA")
        enc_model.to("cuda")
        past_target.to("cuda")
        
    if verbose > 0: print("get_enc_embs_moirai | Get Outputs")

    
    past_observed_target = torch.ones_like(past_target, dtype=torch.bool)
    past_is_pad = torch.zeros_like(past_target, dtype=torch.bool)[...,:,-1] # Kill last dimension

    if (verbose > 1):
        print(f"--> get_enc_embs_moirai | past_target ~ {past_target.shape}")
        print(f"--> get_enc_embs_moirai | past_observed_target ~ {past_observed_target.shape}")
        print(f"--> get_enc_embs_moirai | past_is_pad ~ {past_is_pad.shape}")
        print(f"--> get_enc_embs_moirai | Auxiliar model")
        print(f"--> get_enc_embs_moirai | Auxiliar model | Before Memory:")
        gpu_memory_status()
    
    # Auxiliar model for conversions just to ensure correct sizes
    #not neccesary, is the same module initially downloaded...
    #module = moirai.MoiraiModule.from_pretrained(f"Salesforce/moirai-1.1-R-small")
    
    forecast_model =  moirai_forecast.MoiraiForecast(
        module=enc_model,
        prediction_length=past_target.shape[2], #random, just for getting the model
        context_length=past_target.shape[1],
        patch_size=patch_size,
        num_samples=100, #Random, is the number of forecasting, not interesting for us
        target_dim=past_target.shape[2],
        feat_dynamic_real_dim=0,
        past_feat_dynamic_real_dim=0,
    )
    
    if verbose > 0:
        print(f"--> get_enc_embs_moirai | Auxiliar model | After Memory:")
        gpu_memory_status()
        print(f"--> get_enc_embs_moirai | Convert sizes")
    (
    target,
    observed_mask,
    sample_id,
    time_id,
    variate_id,
    prediction_mask,
    ) = forecast_model._convert(
        patch_size,
        past_target,
        past_observed_target,
        past_is_pad
    )
    if verbose > 1:
        print(f"get_enc_embs_moirai | target ~ {target.shape}")
        print(f"get_enc_embs_moirai | observed_mask ~ {observed_mask.shape}")
        print(f"get_enc_embs_moirai | sample_id ~ {sample_id.shape}")
        print(f"get_enc_embs_moirai | time_id ~ {time_id.shape}")
        print(f"get_enc_embs_moirai | variate_id ~ {variate_id.shape}")
        print(f"get_enc_embs_moirai | prediction_mask ~ {prediction_mask.shape}")
        gpu_memory_status()
    forecast_model = None
    torch.cuda.empty_cache()
    if verbose > 0:
        print(f"--> get_enc_embs_moirai | Delete Auxiliar model | After Memory:")
        gpu_memory_status()
    
    model_kwargs={
        'target': target, 
        'observed_mask': observed_mask,
        'sample_id': sample_id,
        'time_id': time_id,
        'variate_id': variate_id,
        'prediction_mask': prediction_mask,
        'patch_size': torch.ones_like(sample_id, dtype = torch.float32)*patch_size
    } 
    if verbose > 0: 
        print(f"get_enc_embs_moirai | About to get activations")
    acts = get_acts(
        model  = enc_model, 
        module = enc_model.encoder.norm, 
        cpu    = cpu,
        verbose = verbose,
        **model_kwargs #Parameters of the model
    )
    
    embs = acts[0]
    acts = None
    if average_seq_dim :
        if verbose > 0: 
            print(f"get_enc_embs_moirai | About to reduce activations")
        embs = embs.mean(dim = 1)
    
    if to_numpy: 
        if verbose > 0: 
            print(f"get_enc_embs_moirai | About to convert to numpy")
        if cpu:
            embs = embs.numpy() 
        else: 
            embs = embs.cpu().numpy()
    if not cpu:
        enc_input.cpu()
        enc_model.cpu()
        torch.cuda.empty_cache()
    if verbose > 0: 
        print(f"get_enc_embs_moirai | embs ~ embs.shape")
        print("get_enc_embs_moirai -->")
    return embs

# %% ../nbs/encoder.ipynb 28
def get_enc_embs(
    X               , 
    enc_learn       : Learner, 
    module          : str  = None, 
    cpu             : bool = False, 
    average_seq_dim : bool = True, 
    to_numpy        : bool = True,
    verbose         : int  = 0,
    **kwargs        
):
    embs = None
    enc_learn_class = str(enc_learn.__class__)[8:-2]
    match enc_learn_class:
        case "momentfm.models.moment.MOMENTPipeline":
            match enc_learn.task_name:
                case "embedding":
                    embs = get_enc_embs_moment(X, enc_learn, cpu, to_numpy, verbose, average_seq_dim, **kwargs)
                case "reconstruction":
                    embs = get_enc_embs_moment_reconstruction(X, enc_learn, cpu, to_numpy, verbose, average_seq_dim, **kwargs)
                case _:
                    print(f"Model embeddings for moment-{enc_learn.task_name} is not yet implemented.")
        case "fastai.learner.Learner":
            embs = get_enc_embs_MVP_set_stride_set_batch_size(X, enc_learn, stride, batch_size, module, cpu, average_seq_dim, to_numpy, verbose, False, 0, False)
        case "uni2ts.model.moirai.module.MoiraiModule":
            embs = get_enc_embs_moirai(
                enc_input  = X, 
                enc_model  = enc_learn,
                cpu        = cpu, 
                average_seq_dim = average_seq_dim,
                to_numpy   = to_numpy,
                verbose    = verbose,
                **kwargs
            )
        case _:
            print(f"Model embeddings implementation is not yet implemented for {enc_learn_class}.")
    return embs

# %% ../nbs/encoder.ipynb 29
def get_enc_embs_set_stride_set_batch_size(
    X                  : List [ List [ List [ float ] ] ], 
    enc_learn          : Learner, 
    stride             : int, 
    batch_size         : int, 
    module             : str  = None, 
    cpu                : bool = False, 
    average_seq_dim    : bool = True, 
    to_numpy           : bool = True, 
    verbose            : int  = 0, 
    time_flag          : bool = False, 
    chunk_size         : int  = 0, 
    check_memory_usage : bool = False,
    **kwargs
):            
    embs = None
    enc_learn_class = str(enc_learn.__class__)[8:-2]
    match enc_learn_class:
        case "momentfm.models.moment.MOMENTPipeline":
            if verbose > 0: 
                print(f"get_enc_embs_set_stride_set_batch_size | Moment | {average_seq_dim}")
            match enc_learn.task_name:
                case "embedding":
                    embs = get_enc_embs_moment(X, enc_learn, cpu, to_numpy, verbose, average_seq_dim, **kwargs)
                case "reconstruction":
                    embs = get_enc_embs_moment_reconstruction(X, enc_learn, cpu, to_numpy, verbose, average_seq_dim, **kwargs)
                case _:
                    print(f"Model embeddings for moment-{enc_learn.task_name} is not yet implemented.")
        case "fastai.learner.Learner":
            if verbose > 0: 
                print(f"get_enc_embs_set_stride_set_batch_size | MVP | {average_seq_dim}")
            embs = get_enc_embs_MVP_set_stride_set_batch_size(
                X = X, 
                enc_learn = enc_learn, 
                stride = stride, 
                batch_size = batch_size, 
                module = module, 
                cpu = cpu, 
                average_seq_dim = average_seq_dim,
                to_numpy = to_numpy, 
                verbose = verbose, 
                time_flag = time_flag, 
                chunk_size = chunk_size, 
                check_memory_usage = check_memory_usage
            )
        case "uni2ts.model.moirai.module.MoiraiModule":
            if verbose > 0: 
                print(f"get_enc_embs_set_stride_set_batch_size | Moirai | {average_seq_dim}")
            embs = get_enc_embs_moirai(
                enc_input  = X, 
                enc_model  = enc_learn,
                cpu        = cpu, 
                average_seq_dim = average_seq_dim,
                to_numpy   = to_numpy,
                verbose    = verbose,
                **kwargs
            )
        case _:
            print(f"[ get_enc_embs_set_stride_set_batch_size ] Model embeddings implementation is not yet implemented for {enc_learn_class}.")
    # Ñapa: TODO: Gestionar que no se queden en memoria los modelos porque ocupan el 40% de la GPU al llamarlos desde R
    if cpu:
        #X.cpu()
        enc_learn.cpu()
        try: 
            enc_lear.dls.cpu()
        except Exception as e: 
            print(f"Exception: {e}")
        #kwargs_to_cpu_(**kwargs)
    return embs
