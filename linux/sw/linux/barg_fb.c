// SPDX-License-Identifier: GPL-2.0
/*
 * Framebuffer of the BARG SoC's GPU: 320 x 240, RGB565, in the GPU's video memory (0x3010_0000 in the GPU window).
 *
 * The GPU's host bus takes word accesses only (sub-word stores to the window are dropped), so the frame lives in ordinary RAM and a deferred
 * worker copies the rows that changed to the video memory with 32-bit stores. Writers: the framebuffer console and write() (rows are noted by
 * the drawing wrappers below) and mmap() users (the page list of the deferred-IO core).
 */
#include <linux/module.h>
#include <linux/platform_device.h>
#include <linux/fb.h>
#include <linux/io.h>
#include <linux/mm.h>
#include <linux/vmalloc.h>
#include <linux/of.h>
#include <linux/spinlock.h>

#define BFB_W 320
#define BFB_H 240
#define BFB_LINE (BFB_W * 2)
#define BFB_SIZE (BFB_LINE * BFB_H)

struct barg_fb {
	void __iomem *vram;
	spinlock_t lock;
	u32 lo, hi;		/* dirty rows [lo, hi) */
	u32 pseudo_palette[16];
};

static void bfb_mark(struct fb_info *info, u32 y0, u32 y1)
{
	struct barg_fb *par = info->par;
	unsigned long flags;

	if (y1 > BFB_H)
		y1 = BFB_H;
	if (y0 >= y1)
		return;
	spin_lock_irqsave(&par->lock, flags);
	if (par->lo >= par->hi) {
		par->lo = y0;
		par->hi = y1;
	} else {
		par->lo = min(par->lo, y0);
		par->hi = max(par->hi, y1);
	}
	spin_unlock_irqrestore(&par->lock, flags);
	schedule_delayed_work(&info->deferred_work, info->fbdefio->delay);
}

static void bfb_deferred(struct fb_info *info, struct list_head *pagereflist)
{
	struct barg_fb *par = info->par;
	struct fb_deferred_io_pageref *pageref;
	unsigned long flags;
	u32 lo, hi, y;
	const u32 *src;

	list_for_each_entry(pageref, pagereflist, list) {
		u32 y0 = pageref->offset / BFB_LINE;
		u32 y1 = (pageref->offset + PAGE_SIZE + BFB_LINE - 1) / BFB_LINE;

		spin_lock_irqsave(&par->lock, flags);
		if (par->lo >= par->hi) {
			par->lo = y0;
			par->hi = min_t(u32, y1, BFB_H);
		} else {
			par->lo = min(par->lo, y0);
			par->hi = max(par->hi, min_t(u32, y1, BFB_H));
		}
		spin_unlock_irqrestore(&par->lock, flags);
	}
	spin_lock_irqsave(&par->lock, flags);
	lo = par->lo;
	hi = par->hi;
	par->lo = par->hi = 0;
	spin_unlock_irqrestore(&par->lock, flags);
	for (y = lo; y < hi; y++) {
		u32 k;

		src = (const u32 *)(info->screen_buffer + y * BFB_LINE);
		for (k = 0; k < BFB_LINE / 4; k++)
			writel(src[k], par->vram + y * BFB_LINE + 4 * k);
	}
}

static struct fb_deferred_io bfb_defio = {
	.delay = 1,	/* one jiffy: the simulated machine is slow, a longer delay is minutes of real time */
	.deferred_io = bfb_deferred,
};

static int bfb_setcolreg(unsigned int regno, unsigned int red, unsigned int green, unsigned int blue, unsigned int transp, struct fb_info *info)
{
	if (regno >= 16)
		return 1;
	((u32 *)info->pseudo_palette)[regno] = (red & 0xf800) | ((green & 0xfc00) >> 5) | ((blue & 0xf800) >> 11);
	return 0;
}

static void bfb_fillrect(struct fb_info *info, const struct fb_fillrect *r)
{
	sys_fillrect(info, r);
	bfb_mark(info, r->dy, r->dy + r->height);
}

static void bfb_copyarea(struct fb_info *info, const struct fb_copyarea *a)
{
	sys_copyarea(info, a);
	bfb_mark(info, a->dy, a->dy + a->height);
}

static void bfb_imageblit(struct fb_info *info, const struct fb_image *im)
{
	sys_imageblit(info, im);
	bfb_mark(info, im->dy, im->dy + im->height);
}

static ssize_t bfb_write(struct fb_info *info, const char __user *buf, size_t count, loff_t *ppos)
{
	u32 pos = (u32)*ppos;	/* below BFB_SIZE: 32-bit arithmetic only */
	ssize_t ret = fb_sys_write(info, buf, count, ppos);

	if (ret > 0)
		bfb_mark(info, pos / BFB_LINE, ((u32)pos + (u32)ret + BFB_LINE - 1) / BFB_LINE);
	return ret;
}

static const struct fb_ops bfb_ops = {
	.owner = THIS_MODULE,
	.fb_read = fb_sys_read,
	.fb_write = bfb_write,
	.fb_setcolreg = bfb_setcolreg,
	.fb_fillrect = bfb_fillrect,
	.fb_copyarea = bfb_copyarea,
	.fb_imageblit = bfb_imageblit,
	.fb_mmap = fb_deferred_io_mmap,
};

static int bfb_probe(struct platform_device *pdev)
{
	struct fb_info *info;
	struct barg_fb *par;
	void *buf;
	u32 y, k;
	int ret;

	info = framebuffer_alloc(sizeof(*par), &pdev->dev);
	if (!info)
		return -ENOMEM;
	par = info->par;
	spin_lock_init(&par->lock);
	par->vram = devm_platform_ioremap_resource(pdev, 0);
	if (IS_ERR(par->vram)) {
		ret = PTR_ERR(par->vram);
		goto err_release;
	}
	buf = vzalloc(PAGE_ALIGN(BFB_SIZE));
	if (!buf) {
		ret = -ENOMEM;
		goto err_release;
	}
	info->screen_buffer = buf;
	info->fbops = &bfb_ops;
	info->flags = FBINFO_VIRTFB;
	info->pseudo_palette = par->pseudo_palette;
	strscpy(info->fix.id, "barg-gpufb", sizeof(info->fix.id));
	info->fix.type = FB_TYPE_PACKED_PIXELS;
	info->fix.visual = FB_VISUAL_TRUECOLOR;
	info->fix.line_length = BFB_LINE;
	info->fix.smem_len = PAGE_ALIGN(BFB_SIZE);
	info->var.xres = info->var.xres_virtual = BFB_W;
	info->var.yres = info->var.yres_virtual = BFB_H;
	info->var.bits_per_pixel = 16;
	info->var.red.offset = 11; info->var.red.length = 5;
	info->var.green.offset = 5; info->var.green.length = 6;
	info->var.blue.offset = 0; info->var.blue.length = 5;
	info->var.activate = FB_ACTIVATE_NOW;
	info->var.height = info->var.width = -1;
	info->fbdefio = &bfb_defio;
	fb_deferred_io_init(info);
	/* start from a cleared video memory */
	for (y = 0; y < BFB_H; y++)
		for (k = 0; k < BFB_LINE / 4; k++)
			writel(0, par->vram + y * BFB_LINE + 4 * k);
	ret = register_framebuffer(info);
	if (ret < 0)
		goto err_defio;
	platform_set_drvdata(pdev, info);
	dev_info(&pdev->dev, "framebuffer %dx%d RGB565 in the GPU video memory\n", BFB_W, BFB_H);
	return 0;
err_defio:
	fb_deferred_io_cleanup(info);
	vfree(buf);
err_release:
	framebuffer_release(info);
	return ret;
}

static const struct of_device_id bfb_of_match[] = {
	{ .compatible = "barg,gpu-fb" },
	{ }
};
MODULE_DEVICE_TABLE(of, bfb_of_match);

static struct platform_driver bfb_driver = {
	.probe = bfb_probe,
	.driver = { .name = "barg-gpufb", .of_match_table = bfb_of_match },
};
builtin_platform_driver(bfb_driver);

MODULE_DESCRIPTION("Framebuffer on the BARG SoC GPU video memory");
MODULE_LICENSE("GPL");
