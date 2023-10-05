from typing import List, Dict, Any, Tuple

import pytorch_lightning as pl
import torch
from pytorch_lightning.loggers import TensorBoardLogger
from torch import nn
from torch.optim import Optimizer

from src.losses.ocr2 import STRFLInference
from src.pipelines.utils import torch2numpy
from src.utils.draw import draw_word


#
# class SimpleGANEditing(pl.LightningModule):
#     def __init__(
#             self,
#             generator: nn.Module,
#             discriminator: nn.Module,
#             generator_optimizer: Optimizer,
#             discriminator_optimizer: Optimizer,
#             criterions: List[Dict[str, Any]],
#             g_criterions: List[Dict[str, Any]],
#             d_criterions: List[Dict[str, Any]],
#             style_key: str = 'image',
#             draw_orig: str = 'draw_orig',
#             text_orig: str = 'content',
#             draw_rand: str = 'draw_random',
#             text_rand: str = 'random',
#     ):
#         super().__init__()
#         self.generator = generator
#         self.discriminator = discriminator
#         self.generator_optimizer = generator_optimizer
#         self.discriminator_optimizer = discriminator_optimizer
#         self.criterions = criterions
#         self.g_criterions = g_criterions
#         self.d_criterions = d_criterions
#         self.style_key = style_key
#         self.draw_orig = draw_orig
#         self.text_orig = text_orig
#         self.draw_rand = draw_rand
#         self.text_rand = text_rand
#
#     def forward(self, style, content, postfix='base'):
#         results = self.generator(style, content)
#         if not isinstance(results, dict):
#             results = {'pred': results}
#         results = {f"{key}{postfix}": value for key, value in results.items()}
#         return results
#
#     def training_step(self, batch, batch_idx):
#         style = batch[self.style_key]
#         draw_orig = batch[self.draw_orig]
#         draw_rand = batch[self.draw_rand]
#
#         self.toggle_optimizer(self.generator_optimizer, 0)
#         predictions = self.forward(style, draw_rand, '_base')
#         # predictions.update(self.forward(style, draw_orig, '_original'))
#         predictions.update(batch)
#
#         total = 0
#         for criterion_dict in self.criterions:
#             criterion, name, pred_key, target_key = [criterion_dict[key] for key in
#                                                      ['criterion', 'name', 'pred_key', 'target_key']]
#             loss = criterion(predictions[pred_key], predictions[target_key])
#             self.log(name, loss)
#             total = loss + total
#
#         for criterion_dict in self.g_criterions:
#             criterion, name, real_key, fake_key = [criterion_dict[key] for key in
#                                                    ['criterion', 'name', 'real', 'fake']]
#             loss = criterion(predictions[real_key], predictions[fake_key])
#             self.log(name, loss)
#             total = loss + total
#
#         self.log('total', total)
#
#         self.manual_backward(total)
#         self.generator_optimizer.step()
#         self.generator_optimizer.zero_grad()
#         self.untoggle_optimizer(0)
#
#         for criterion_dict in self.d_criterions:
#             criterion, name, real_key, fake_key = [criterion_dict[key] for key in
#                                                    ['criterion', 'name', 'real', 'fake']]
#             loss = criterion(predictions[real_key], predictions[fake_key])
#             self.log(name, loss)
#             total = loss + total
#
#         criterion, name, real_key, fake_key = [self.d_criterion[key] for key in ['criterion', 'name', 'real', 'fake']]
#
#         return total
#
#     def configure_optimizers(self):
#         return [self.generator_optimizer, self.discriminator_optimizer], []


class SimpleGAN(pl.LightningModule):
    def __init__(
            self,
            generator: nn.Module,
            discriminator: nn.Module,
            generator_optimizer: Optimizer,
            discriminator_optimizer: Optimizer,
            criterions: List[Dict[str, Any]],
            g_criterions: List[Dict[str, Any]],
            d_criterions: List[Dict[str, Any]],
            metrics: List[Dict[str, Any]],
            style_key: str = 'image',
            draw_orig: str = 'draw_orig',
            text_orig: str = 'content',
            draw_rand: str = 'draw_random',
            text_rand: str = 'random',
            mean: Tuple[float, float, float] = (0.485, 0.456, 0.406),
            std: Tuple[float, float, float] = (0.229, 0.224, 0.225),
    ):
        super().__init__()
        self.generator = generator
        self.discriminator = discriminator
        self.generator_optimizer = generator_optimizer
        self.discriminator_optimizer = discriminator_optimizer
        self.criterions = criterions
        self.g_criterions = g_criterions
        self.d_criterions = d_criterions
        self.metrics = metrics
        self.style_key = style_key
        self.draw_orig = draw_orig
        self.text_orig = text_orig
        self.draw_rand = draw_rand
        self.text_rand = text_rand
        self.mean = mean
        self.std = std

        self.ocr = STRFLInference(mean, std)
        self.automatic_optimization = False

    def forward(self, style, content, postfix='base'):
        results = self.generator(style, content)
        if not isinstance(results, dict):
            results = {'pred': results}
        results = {f"{key}{postfix}": value for key, value in results.items()}
        return results

    def training_step(self, batch, batch_idx):
        style = batch[self.style_key]
        draw_orig = batch[self.draw_orig]
        draw_rand = batch[self.draw_rand]

        self.toggle_optimizer(self.generator_optimizer, 0)
        predictions = self.forward(style, draw_rand, '_base')
        predictions.update(self.forward(style, draw_orig, '_original'))
        predictions.update(batch)

        total = 0
        for criterion_dict in self.criterions:
            criterion, name, pred_key, target_key = [criterion_dict[key] for key in
                                                     ['criterion', 'name', 'pred_key', 'target_key']]
            loss = criterion(predictions[pred_key], predictions[target_key])
            self.log(name, loss)
            total = loss + total

        for criterion_dict in self.g_criterions:
            criterion, name, real_key, fake_key = [criterion_dict[key] for key in
                                                   ['criterion', 'name', 'real', 'fake']]
            loss = criterion(
                self.discriminator(predictions[real_key]),
                self.discriminator(predictions[fake_key])
            )
            self.log(name, loss)
            total = loss + total

        self.log('total', total)

        self.manual_backward(total)
        self.untoggle_optimizer(0)

        self.toggle_optimizer(self.discriminator_optimizer, 1)

        disc = 0
        for criterion_dict in self.d_criterions:
            criterion, name, real_key, fake_key = [criterion_dict[key] for key in
                                                   ['criterion', 'name', 'real', 'fake']]
            loss = criterion(
                self.discriminator(predictions[real_key]),
                self.discriminator(predictions[fake_key].detach())
            )
            self.log(name, loss)
            disc = loss + disc

        self.manual_backward(disc)
        self.untoggle_optimizer(1)

        self.generator_optimizer.step()
        self.generator_optimizer.zero_grad()
        self.discriminator_optimizer.step()
        self.discriminator_optimizer.zero_grad()

    def visualize_image(self, name, image):
        tb_logger = None
        for logger in self.trainer.loggers:
            if isinstance(logger, TensorBoardLogger):
                tb_logger = logger.experiment
                break

        if tb_logger is None:
            raise ValueError('TensorBoard Logger not found')

        draw = image
        if isinstance(image, torch.Tensor):
            draw = torch2numpy(image, self.mean, self.std)

        if draw.shape[2] == 3:
            draw = draw.transpose((2, 0, 1)).copy()

        tb_logger.add_image(name, draw, self.current_epoch)

    def validation_step(self, batch, batch_idx):
        style = batch[self.style_key]
        draw_orig = batch[self.draw_orig]
        draw_rand = batch[self.draw_rand]

        predictions = self.forward(style, draw_rand, '_base')
        predictions.update(self.forward(style, draw_orig, '_original'))
        predictions.update(batch)

        total = 0
        for criterion_dict in self.criterions:
            criterion, name, pred_key, target_key = [criterion_dict[key] for key in
                                                     ['criterion', 'name', 'pred_key', 'target_key']]
            loss = criterion(predictions[pred_key], predictions[target_key])
            self.log(f'val/{name}', loss)

            total = loss + total
        self.log('val/total', total)

        for metric_dict in self.metrics:
            metric, name, pred_key, target_key = [metric_dict[key] for key in
                                                  ['metric', 'name', 'pred_key', 'target_key']]
            metric.update(predictions[pred_key], predictions[target_key])

        if batch_idx == 0:
            recogs_base = self.ocr.recognize(predictions['pred_original'])
            recogs_rand = self.ocr.recognize(predictions['pred_base'])
            for i in range(10):
                self.visualize_image(f'{i}/image', predictions[self.style_key][i])
                self.visualize_image(f'{i}/pred_base', predictions['pred_base'][i])
                self.visualize_image(f'{i}/pred_original', predictions['pred_original'][i])

                self.visualize_image(f'{i}/draw_orig', predictions[self.draw_orig][i])
                self.visualize_image(f'{i}/draw_rand', predictions[self.draw_rand][i])

                self.visualize_image(f'{i}/recog_orig', draw_word(recogs_base[i]))
                self.visualize_image(f'{i}/recog_rand', draw_word(recogs_rand[i]))

    def validation_epoch_end(self, outputs) -> None:
        for metric_dict in self.metrics:
            res = metric_dict['metric'].compute()
            self.log(metric_dict['name'], res)
            metric_dict['metric'].reset()

    def configure_optimizers(self):
        return [self.generator_optimizer, self.discriminator_optimizer], []
