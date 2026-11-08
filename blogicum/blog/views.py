from django.utils import timezone
from django.db.models import Count
from django.views.generic import CreateView, UpdateView, DetailView
from django.urls import reverse_lazy
from django.core.paginator import Paginator
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth import update_session_auth_hash, get_user_model
from django.http import Http404, HttpResponseForbidden
from django.conf import settings

from blog.forms import PostForm, CommentForm, ProfileForm, PasswordChangeForm
from blog.models import Post, Category, Comment

User = get_user_model()


def profile_view(request, username):
    user = get_object_or_404(User, username=username)
    posts = user.posts.annotate(comment_count=Count('comments'))

    if request.user.username != username:
        posts = posts.filter(
            is_published=True,
            category__is_published=True,
            pub_date__lte=timezone.now(),
        )

    page_number = request.GET.get('page', 1)
    paginator = Paginator(posts.order_by('-pub_date'), settings.LIMIT_POSTS)
    page_obj = paginator.get_page(page_number)

    context = {
        'profile': user,
        'page_obj': page_obj,
    }
    return render(request, 'blog/profile.html', context)


class ProfileUpdateView(LoginRequiredMixin, UpdateView):
    model = User
    form_class = ProfileForm
    template_name = 'blog/user.html'

    def get_object(self, queryset=None):
        return self.request.user

    def get_success_url(self):
        return reverse_lazy(
            'blog:profile', kwargs={'username': self.request.user.username}
        )


@login_required
def password_change_view(request, username):
    form = PasswordChangeForm(request.user, request.POST or None)
    if not form.is_valid():
        context = {'form': form}
        return render(request, 'blog/password_change_form.html', context)

    user = form.save()
    update_session_auth_hash(request, user)
    return redirect('blog:password_change_done')


class PostMixin:
    model = Post
    form_class = PostForm
    template_name = 'blog/create.html'


class PostCreateView(LoginRequiredMixin, PostMixin, CreateView):
    def form_valid(self, form):
        form.instance.author = self.request.user
        return super().form_valid(form)


class PostUpdateView(LoginRequiredMixin, PostMixin, UpdateView):
    pk_url_kwarg = 'post_id'

    def dispatch(self, request, *args, **kwargs):
        if self.get_object().author != request.user:
            return redirect('blog:post_detail', **kwargs)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['is_edit'] = True
        return context


@login_required
def delete_post(request, post_id):
    post = get_object_or_404(Post, pk=post_id, author=request.user)
    if request.method != 'POST':
        context = {
            'post': post,
            'is_delete': True,
        }
        return render(request, 'blog/create.html', context)
    post.delete()
    return redirect('blog:profile', request.user.username)


class PostDetailView(DetailView):
    model = Post
    template_name = 'blog/detail.html'
    context_object_name = 'post'
    pk_url_kwarg = 'post_id'

    def get_object(self):
        post = super().get_object()
        user = self.request.user

        if user == post.author:
            return post

        if (
            (post.category is None or not post.category.is_published)
            or not post.is_published
            or post.pub_date > timezone.now()
        ):
            raise Http404("Публикация не найдена или недоступна")

        return post

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = CommentForm()
        context['comments'] = self.object.comments.select_related('author')
        return context


def index(request):
    post_list = (
        Post.objects.select_related('category')
        .annotate(comment_count=Count('comments'))
        .filter(
            pub_date__lte=timezone.now(),
            is_published=True,
            category__is_published=True,
        )
        .order_by('-pub_date')
    )
    page_number = request.GET.get('page', 1)
    paginator = Paginator(post_list, settings.LIMIT_POSTS)
    page_obj = paginator.get_page(page_number)
    context = {'page_obj': page_obj}
    return render(request, 'blog/index.html', context)


def category_posts(request, category_slug):
    category = get_object_or_404(
        Category, slug=category_slug, is_published=True
    )
    post_list = (
        category.posts.annotate(comment_count=Count('comments'))
        .filter(
            is_published=True,
            pub_date__lte=timezone.now(),
        )
        .order_by('-pub_date')
    )
    page_number = request.GET.get('page', 1)
    paginator = Paginator(post_list, settings.LIMIT_POSTS)
    page_obj = paginator.get_page(page_number)
    context = {'category': category, 'page_obj': page_obj}
    return render(request, 'blog/category.html', context)


@login_required
def add_comment(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    form = CommentForm(request.POST)
    if not form.is_valid():
        return redirect('blog:post_detail', post_id)
    comment = form.save(commit=False)
    comment.author = request.user
    comment.post = post
    comment.save()
    return redirect('blog:post_detail', post_id)


@login_required
def edit_comment(request, post_id, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.author != request.user:
        return HttpResponseForbidden(
            'У вас нет прав для редактирования этого комментария.'
        )
    form = CommentForm(request.POST or None, instance=comment)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('blog:post_detail', post_id)
    context = {
        'form': form,
        'comment': comment,
        'is_edit': True,
    }
    return render(request, 'blog/comment.html', context)


@login_required
def delete_comment(request, post_id, comment_id):
    comment = get_object_or_404(Comment, id=comment_id)
    if comment.author != request.user:
        return HttpResponseForbidden(
            'У вас нет прав для удаления этого комментария.'
        )
    if request.method != 'POST':
        context = {
            'comment': comment,
            'is_delete': True,
        }
        return render(request, 'blog/comment.html', context)
    comment.delete()
    return redirect('blog:post_detail', post_id)
